import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
const noComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<![:'"`])\/\/[^\n]*/g, "");
/** Тіло функції `name` у джерелі `src` (від `{` після сигнатури до парної `}`). */
function fn(src, name) {
  const m = new RegExp(`(?:async )?function ${name}\\(`).exec(src);
  assert.ok(m, `функції ${name} нема`);
  const open = src.indexOf("{", src.indexOf(")", m.index));
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) return noComments(src.slice(open, i + 1)); }
  }
  throw new Error(`немає закриття для ${name}`);
}
const W = read("wizard.js");

test("контролер не імпортує app.js (усе — залежностями)", () => {
  assert.doesNotMatch(W, /from ["']\.\/app\.js["']/);
});

test("кожен запит кроків 2–4 несе простір майстра (`space: mine.spaceId` / `space=`), а не «поточний»", () => {
  assert.match(fn(W, "loadStep2"), /\/api\/modules\?space=\$\{encodeURIComponent\(mine\.spaceId\)\}/);
  assert.match(fn(W, "loadStep3"), /\/api\/modules\?space=\$\{encodeURIComponent\(mine\.spaceId\)\}/);
  assert.match(fn(W, "submit3"), /\/api\/modules\?space=\$\{encodeURIComponent\(mine\.spaceId\)\}/);
  assert.match(fn(W, "runOp"), /writePayload\(mine\.spaceId, op\.id,/);
  assert.match(fn(W, "runOp"), /\{ space: mine\.spaceId, id: op\.id \}/);
  assert.match(fn(W, "submit4"), /space: mine\.spaceId/);
});

test("runOp: запис модуля (`entry`) іде третім аргументом post для enable|settings — стеля запиту за його check_timeout_s; disable — без нього", () => {
  const b = fn(W, "runOp");
  assert.match(b, /op\.op === "disable" \? deps\.post\(path, body\) : deps\.post\(path, body, card\?\.entry \?\? fresh\.find\(\(e\) => e\?\.id === op\.id\)\)/);
});

test("заміна в ролі — `replace` лише для enable; stale-запис не шлеться", () => {
  const b = fn(W, "runOp");
  assert.match(b, /op\.op === "enable"\)/);
  assert.match(b, /if \(op\.stale\.length\)/);
  assert.ok(b.indexOf("op.stale.length") < b.indexOf("deps.post("), "перевірка свіжості — до запиту");
});

test("план записів знає список кроку 2 (зниклий вибір не вимикає постачальника); вибір чиститься від зниклих", () => {
  assert.match(fn(W, "submit3"), /prevList: mine\.list2/);
  assert.match(fn(W, "loadStep2"), /mine\.list2 = mine\.list/);
  assert.match(fn(W, "loadStep2"), /prunePick\(mine\.pick, mine\.list\)/);
  assert.match(fn(W, "loadStep3"), /prunePick\(mine\.pick, mine\.list\)\.size !== mine\.pick\.size/);
});

test("залежне вимкнення — лише після записаної заміни; рядки «вимкнеться» — з `replaced` відповіді", () => {
  const b = fn(W, "runOp");
  assert.match(b, /op\.after\.some\(\(id\) => pass\.written\.has\(id\)\)/);
  assert.match(b, /pass\.replaced\.has\(op\.id\)/);
  assert.match(b, /r\?\.replaced/);
  assert.ok(b.indexOf("pass.written.has") < b.indexOf("deps.post("), "перевірка заміни — до запиту");
});

test("після проходу знімок свіжості переходить на новий стан лише для ролей, яких торкнувся сам прохід", () => {
  const b = fn(W, "submit3");
  assert.match(b, /for \(const role of pass\.touched\) mine\.atPick\.set\(role, now\.get\(role\) \?\? \[\]\)/);
  assert.match(fn(W, "runOp"), /pass\.touched\.add\(role\)/);
  assert.doesNotMatch(b, /mine\.atPick = holdersByRole/);
});

test("крок 3 без списку: «Повторити» перечитує крок 3, а «Зберегти» спершу повторює; фокус після відмови не губиться", () => {
  assert.match(fn(W, "click"), /if \(wz\.step === 3\) loadStep3\(\); else loadStep2\(\);/);
  const b = fn(W, "submit3");
  assert.ok(b.indexOf("if (wz.s3failed)") < b.indexOf("capture("), "перевірка s3failed — до читання форми");
  assert.match(b, /\?\? box\)\?\.focus/);
  assert.match(fn(W, "submit1"), /clearError\(form\)/);
  assert.match(fn(W, "submit4"), /clearError\(form\)/);
});

test("обовʼязкові поля — до будь-якого запиту кроку 3", () => {
  const b = fn(W, "submit3");
  assert.ok(b.indexOf("missingRequired(") < b.indexOf("deps.api("), "missingRequired після запиту");
});

test("секрети: перемальовка бере їх у локальну мапу й вертає ВЛАСТИВІСТЮ .value; після відповіді — порожньо", () => {
  assert.match(fn(W, "paint"), /for \(const \[id, v\] of keep\.secrets\)/);
  assert.match(fn(W, "paint"), /\.value = v/);
  assert.doesNotMatch(fn(W, "paint"), /setAttribute\(["']value/);
  assert.match(fn(W, "runOp"), /clearSecrets\(op\.id\)/);
  assert.doesNotMatch(W, /wz\.[a-z0-9]*\.secrets\s*=/i, "секрети в стані майстра");
});

test("після будь-якого успішного запису модулів — легкий шлях оболонки (afterModulesChange), а не перемикання простору", () => {
  const b = fn(W, "submit3");
  assert.match(b, /await deps\.afterModulesChange\(\)/);
  assert.doesNotMatch(b, /afterSpaceCreated/);
});

test("вихід із незбереженим кроком 3 питає; Esc сторінку не закриває (обробника клавіш нема)", () => {
  assert.match(fn(W, "requestExit"), /if \(dirty\(\) && !\(await askDiscard\(\)\)\) return;/);
  assert.match(fn(W, "back"), /dirty\(\) && !\(await askDiscard\(\)\)/);
  assert.doesNotMatch(W, /keydown/);
});

test("простір створено — оболонка дізнається навіть тоді, коли майстер тим часом закрили", () => {
  const b = fn(W, "submit1");
  const asc = b.indexOf("await deps.afterSpaceCreated()");
  const guard = b.indexOf("if (wz !== mine) return;", asc);
  assert.ok(asc > 0 && guard > asc, "перевірка «майстер ще той» — ПІСЛЯ повідомлення оболонки");
  assert.ok(b.indexOf("go(2)", guard) > guard);
  /* `created` і `busy` — після повідомлення оболонки, а не до: перемальовка у вікні `afterSpaceCreated` не має перемикати
     крок на режим правки з доступним «Далі». `spaceId` — раніше (оболонка читає простір майстра). */
  assert.equal(b.split("mine.created = true").length - 1, 1, "created ставиться один раз");
  assert.ok(b.indexOf("mine.created = true") > guard, "created ставиться після перевірки «майстер ще той»");
  assert.ok(b.indexOf("mine.spaceId = r.id") < asc, "spaceId — до повідомлення оболонки");
});

/* ── що додано після живого прогону контролера (стенд у Chromium): гарди, яких не було в плані ──────────────────── */

test("крок 4: друга відправка, поки перелік id ще вантажиться, не дає другого task-new; зайнятість стає ПІСЛЯ перевірки", () => {
  const b = fn(W, "submit4");
  assert.match(b, /if \(mine\.checking\) return;/);
  assert.ok(b.indexOf("mine.checking = true") < b.indexOf("taskFormError("), "прапорець — до перевірки");
  /* Демо гілка (0.33.0) має власний `setBusy` ДО перевірки — перелік id їй не потрібен; для звичайного шляху — перший `setBusy` ПІСЛЯ зняття прапорця. */
  const off = b.indexOf("mine.checking = false");
  assert.ok(off > 0 && b.indexOf("setBusy(form, true", off) > off, "прапорець знято до зайнятості (далі тримає wz.busy)");
});

test("перемальовка під час запиту кроків 1 і 4 не лишає форму вимкненою й не губить відмову (`setBusy`/`showError` бачать відчеплену форму)", () => {
  const b = fn(W, "setBusy");
  assert.match(b, /busyForm\.isConnected/);
  assert.match(b, /paint\(\)/);
  assert.match(fn(W, "showError"), /form\?\.isConnected/);
});

test("вихід до створення (логотип на кроці 1) — те саме, що «Скасувати» (back: true); openTask, що кинув, не лишає мертву сторінку", () => {
  assert.match(fn(W, "requestExit"), /exit\(mine\.created \? [^;]+ : null, !mine\.created\)/);
  assert.match(fn(W, "submit4"), /catch \(e\) \{ deps\.toast\(t\("errFailed", e\?\.message \?\? ""\)\); deps\.exit\(\{ back: false \}\); \}/);
});

test("фокус не губиться: після «Спробувати ще» (заголовок чи нова «Спробувати ще») і після зайнятості форми", () => {
  assert.match(fn(W, "click"), /wz\.refocus = true/);
  assert.match(fn(W, "afterRetry"), /focusLost\(\)/);
  assert.match(fn(W, "restoreBusyFocus"), /focusLost\(\)/);
  assert.match(fn(W, "loadStep3"), /afterRetry\(mine\)/);
  assert.match(fn(W, "loadStep2"), /afterRetry\(mine\)/);
});

test("правка поля картки кроку 3 знімає і `aria-invalid`, і текст помилки (без позначки він висів би)", () => {
  assert.match(fn(W, "input"), /dropFieldError\(n\)/);
  assert.match(fn(W, "dropFieldError"), /delete card\.errors\[/);
});

/* ── після ревʼю 616c025 (I1–I3, M1–M4) ──────────────────────────────────────────────────────────────────────── */

test("I1: перехід кроку — з верху сторінки; помилки кроку 3 фокусуються з прокруткою (без preventScroll)", () => {
  assert.match(fn(W, "go"), /scrollTop = 0/);
  assert.ok(fn(W, "go").indexOf("scrollTop = 0") < fn(W, "go").indexOf("focusStep()"), "скрол нагору — до фокуса заголовка");
  const b = fn(W, "submit3");
  assert.match(b, /\[aria-invalid="true"\]'\)\?\.focus\(\);/);
  assert.match(b, /\?\? box\)\?\.focus\(\);/);
});

test("I2: щойно записана картка не перечитується з DOM (її базис — відповідь сервера): `fresh` ставить runOp, знімає capture", () => {
  assert.match(fn(W, "runOp"), /Object\.assign\(card, cardFrom\(r\.module\), \{ fresh: true \}\)/);
  assert.match(fn(W, "capture"), /if \(card\.fresh\) \{ delete card\.fresh; continue; \}/);
});

test("I3: збій свіжого списку на початку «Зберегти» не губить набране (без s3failed): тост і фокус на «Зберегти»", () => {
  const b = fn(W, "submit3");
  const i = b.indexOf("catch (e)");
  const tail = b.slice(i, b.indexOf("if (wz !== mine) return;", i + 40));
  assert.doesNotMatch(tail.slice(tail.indexOf("mine.busy = false")), /s3failed/);
  assert.match(tail, /deps\.toast\(t\("cnErrLoad"\)\)/);
  assert.match(tail, /data-a="ok"\]'\)\?\.focus\(\)/);
});

test("M1: після очікування переліку id крок 4 перевіряється ще раз (Назад/Закрити в цьому вікні не створюють задачу)", () => {
  assert.match(fn(W, "submit4"), /if \(wz !== mine \|\| mine\.step !== 4\) return;/);
});

test("M2: зайнятість кроку 3 тримається до кінця проходу (після знімка й afterModulesChange), `busy` кроку 1 — після afterSpaceCreated", () => {
  const b = fn(W, "submit3");
  const am = b.indexOf("await deps.afterModulesChange()");
  const off = b.indexOf("mine.busy = false;", am);
  assert.ok(am > 0 && off > am, "busy=false — після afterModulesChange");
  assert.ok(off < b.indexOf("go(4)"), "busy=false — до go(4)/останньої перемальовки");
  const loop = b.slice(b.indexOf("for (const op of ops)"), am);
  assert.doesNotMatch(loop.replace(/gone-space[^\n]*\n/, ""), /mine\.busy = false/, "між проходом і afterModulesChange busy не знімається");
});

test("M3: після перейменування оболонка дізнається ДО перевірки «майстер ще той»", () => {
  assert.match(fn(W, "submit1"),
    /try \{ deps\.afterSpaceEdited\(mine\.spaceId, saved\); \} catch \(e\) \{ deps\.toast\(t\("errFailed", e\?\.message \?\? ""\)\); \}\s*if \(wz !== mine\) return;/,
    "afterSpaceEdited у try (збій оболонки не заклинює форму) і раніше за перевірку");
});

test("M4: «Назад» і «Закрити» перевіряють після питання, що майстер той самий", () => {
  assert.match(fn(W, "requestExit"), /const mine = wz;\s*if \(dirty\(\) && !\(await askDiscard\(\)\)\) return;\s*if \(wz !== mine\) return;/);
  assert.match(fn(W, "back"), /const mine = wz;\s*if \(wz\.step === 3 && dirty\(\) && !\(await askDiscard\(\)\)\) return;\s*if \(wz !== mine\) return;/);
});

/* ══ app.js: третя сторінка оверлею `wiz`, входи, прибрано діалог «Новий простір» (Task 7) ═══════════════════════════ */

const A = read("app.js");

test("входи: дропдаун/⌘K і привітання ведуть у майстер, «Відкрити наявну теку» — з фокусом у теці", () => {
  assert.match(A, /\n  spacenew: \(\) => openWizard\(\),/);
  assert.match(fn(A, "wireHome"), /case 'spacenew': openWizard\(\); break;/);
  assert.match(fn(A, "wireHome"), /case 'spaceopen': openWizard\(\{ folderFirst: true \}\); break;/);
  assert.doesNotMatch(A, /function openSpaceNew\(/, "старий діалог «Новий простір» лишився");
  assert.match(fn(A, "openWizard"), /wiz\.open\(\{ folderFirst \}\);\s*enterHome\(\{ page: 'wiz' \}\);[\s\S]*?wiz\.focusStep\(\);/);
});

test("сторінка wiz: paintHome малює майстер раніше за привітання; enterHome не тягне список задач; вихід — reset", () => {
  const p = fn(A, "paintHome");
  assert.ok(p.indexOf("homePage === 'wiz'") > -1 && p.indexOf("homePage === 'wiz'") < p.indexOf("needsWelcome("),
    "майстер мусить малюватись і тоді, коли просторів ще нема (перший запуск)");
  const e = fn(A, "enterHome");
  assert.match(e, /if \(next !== 'wiz'\) wiz\.reset\(\);/);
  assert.match(e, /if \(homePage === 'wiz'\) \{\s*homeSeq \+= 1;\s*paintHome\(\);\s*return;\s*\}/);
  assert.match(fn(A, "leaveHome"), /wiz\.reset\(\);/);
});

test("логотип на майстрі — вихід через майстер (питає про незбережене)", () => {
  assert.match(A, /\n  home: async \(\) => \{ if \(homeOpen && homePage === 'wiz'\) \{ await wiz\.requestExit\(\); return; \} if \(cnDrawer && !\(await dismissCnDrawer\(\)\)\) return; await navigating\(\(\) => enterHome\(\{ page: 'tasks' \}\)\); \},/);
});

test("події сторінки майстра йдуть у контролер раніше за обробники «Задач»", () => {
  const w = fn(A, "wireHome");
  assert.match(w, /if \(homePage === 'wiz'\) \{ wiz\.click\(ev\); return; \}/);
  assert.match(w, /addEventListener\('submit', \(ev\) => \{ if \(homePage === 'wiz'\) wiz\.submit\(ev\); \}\)/);
  assert.match(w, /if \(homePage === 'wiz'\) \{ wiz\.input\(ev\); return; \}/);
  /* Радіо модулів і джерела макета працюють на `change`, поля — на `input`: обидва слухачі мусять віддавати подію контролеру. */
  const line = "if (homePage === 'wiz') { wiz.input(ev); return; }";
  assert.equal(w.split(line).length - 1, 2, "wiz.input мусить стояти і в слухачі `input`, і в слухачі `change`");
  const iChange = w.indexOf("addEventListener('change'");
  assert.ok(w.indexOf(line) < iChange && w.indexOf(line, iChange) > iChange, "один — у слуханні `input`, другий — після `change`");
});

test("клавіші «Задач» діють лише на «Задачах»; повернення у вікно майстра не перечитує", () => {
  assert.match(A, /if \(homePage !== 'tasks'\) return;\s+\/\/ «Підключення» й майстер/);
  assert.match(fn(A, "refreshHomeOnReturn"), /if \(homePage === 'wiz'\) return;/);
});

test("залежності контролера: запис модулів — легкий шлях 3a, простір — afterSpaceChange, задача — wizOpenTask", () => {
  assert.match(A, /afterModulesChange: \(\) => afterModulesChange\(\),/);
  assert.match(A, /afterSpaceCreated: \(\) => afterSpaceChange\(\),/);
  assert.match(A, /openTask: \(made\) => wizOpenTask\(made\),/);
  assert.match(A, /exit: \(\{ back = false \} = \{\}\) => \(back \? wizBack\(\) : enterHome\(\{ page: 'tasks' \}\)\),/);
});

/* ── поправка після ревʼю Task 6 (8а) і запити зі стелею часу ──────────────────────────────────────────────────── */

test("8а: секрети живуть у `.value` полів кроку 3 — розмітка майстра зникає з DOM при виході (leaveHome і enterHome з wiz)", () => {
  const l = fn(A, "leaveHome");
  assert.match(l, /wiz\.reset\(\);/);
  assert.match(l, /homeNode\(\)\?\.querySelector\('\.wz'\)\?\.remove\(\);/);
  assert.ok(l.indexOf("querySelector('.wz')") < l.indexOf("await render()"), "прибирання — ДО будь-якого await");
  const e = fn(A, "enterHome");
  assert.match(e, /if \(homePage === 'wiz' && next !== 'wiz'\) homeNode\(\)\?\.querySelector\('\.wz'\)\?\.remove\(\);/);
  assert.ok(e.indexOf("querySelector('.wz')") < e.indexOf("paintHome();"), "прибирання — до перемальовки сторінки");
});

test("запити майстра (space-new, task-new, space-update) — через postForm зі стелею часу, а не голий post", () => {
  assert.match(A, /post: \(p, body, entry\) => \(entry \? checkPost\(p, body, entry\) : postForm\(p, body\)\),/);
  assert.match(A, /takenTaskIds: \(\) => formApi\('\/api\/tasks\?all=1'\)/);
});

test("wizBack: «Скасувати» до створення вертає туди, звідки прийшли, і ставить фокус на фішку простору", () => {
  const b = fn(A, "wizBack");
  assert.match(b, /if \(wizFrom === null && currentTaskId\) await leaveHome\(\);/);
  assert.match(b, /else enterHome\(\{ page: wizFrom === 'conn' \? 'conn' : 'tasks' \}\);/);
  assert.match(b, /\(chipEl\(\) \?\? homeNode\(\)\?\.querySelector\(`\[data-th="\$\{wizOpener\}"\]`\)\)\?\.focus\(\{ preventScroll: true \}\);/);
  assert.match(fn(A, "openWizard"), /wizFrom = homeOpen \? homePage : null;/);
  assert.match(fn(A, "openWizard"), /if \(spacesResp\?\.off\) return;/);
});

test("openWizard не губить брудну панель «Підключення» мовчки: dismissCnDrawer ДО enterHome (як логотип); без панелі — без await", () => {
  const b = fn(A, "openWizard");
  assert.match(b, /if \(cnDrawer && !\(await dismissCnDrawer\(\)\)\) return;/);
  assert.ok(b.indexOf("dismissCnDrawer") < b.indexOf("wizFrom ="), "питання — до запису `wizFrom` (стан міг змінитись, поки питали)");
  assert.ok(b.indexOf("dismissCnDrawer") < b.indexOf("enterHome("), "питання — до того, як `enterHome` закриє панель");
});

test("wizOpenTask: як «Нова задача» на «Задачах» — простір відповіді порівнюється з відомим, homeData скинуто, перехід через leaveHome", () => {
  const b = fn(A, "wizOpenTask");
  assert.match(b, /if \(spaceChanged\(spaceNow\(\)\?\.id, made\.space\)\) await resetSpaceState\(\);\s*else await resetPerTaskState\(\);/);
  assert.match(b, /homeData = null;\s*currentTaskId = made\.id; taskSwitchGen \+= 1;/);
  assert.match(b, /await leaveHome\(\);/);
});

test("barState віддає homePage лише при відкритому оверлеї (смуга й ⌘K знають `wiz`)", () => {
  assert.match(A, /homePage: homeOpen \? homePage : null,/);
});

/* ══ після ревʼю 1c000c3 ═════════════════════════════════════════════════════════════════════════════════════════ */

test("R1: поки крок 1 «зайнятий» (створення, перемальовка з `afterSpaceChange` чи мови), форму проводять як `edit` — без peek: інакше щойно створену теку видно як «вже додано»", () => {
  assert.match(fn(W, "wire"), /mode: wz\.created \|\| wz\.busy \? "edit" : "new"/);
});

test("R2: «Скасувати» на «Підключення» не віддає фокус першій картці: connFocusPending скидається, фокус — фішка (або кнопка-відкривач привітання)", () => {
  const b = fn(A, "wizBack");
  assert.match(b, /if \(wizFrom === 'conn'\) connFocusPending = false;/);
  assert.ok(b.indexOf("enterHome(") < b.indexOf("connFocusPending = false"), "скидання — ПІСЛЯ enterHome (він ставить прапорець)");
  assert.ok(b.indexOf("connFocusPending = false") < b.indexOf(".focus("), "скидання — до фокуса");
});

test("R3: майстер відкривається з верху, а не зі скролом списку задач (скидання ПІСЛЯ enterHome: paint повертає старий скрол)", () => {
  const b = fn(A, "openWizard");
  const i = b.indexOf("enterHome({ page: 'wiz' })");
  assert.match(b, /homeNode\(\)\.scrollTop = 0;|if \(home\) home\.scrollTop = 0;/);
  assert.ok(b.search(/scrollTop = 0/) > i && b.search(/scrollTop = 0/) < b.indexOf("wiz.focusStep()"), "між enterHome і focusStep");
});

test("R4: «Скасувати» з привітання вертає фокус на кнопку, якою майстер відкрили (spaceopen / spacenew)", () => {
  const b = fn(A, "openWizard");
  assert.match(b, /wizOpener = folderFirst \? 'spaceopen' : 'spacenew';/);
  assert.match(A, /let wizOpener = 'spacenew';/);
});

/* Заміна pin-ів колишнього діалогу `openSpaceNew`: його логіка тепер у контролері майстра. */
test("R5: перший простір — «Особисте», колір — перший невикористаний, тека — перша ВІЛЬНА (реєстр), «відкрити теку» — порожня назва й тека", () => {
  const b = fn(W, "open");
  assert.match(b, /const name = needsWelcome\(info\) && !folderFirst \? t\("personalName"\) : "";/);
  assert.match(b, /color: freeColor\(info\?\.spaces\)/);
  assert.match(b, /path: folderFirst \? "" : defaultSpacePath\(name, "~", deps\.takenPaths\(\)\)/);
});

test("R6: крок 1 — запит `space-new` з назвою, кольором і текою; відмова → ключ словника за `e.code` (spaceErrKey) і поле (spaceErrField); `e.key` не читається", () => {
  const b = fn(W, "submit1");
  assert.match(b, /deps\.post\("\/api\/space-new", \{ name, color: mine\.s1\.color, path: mine\.s1\.path\.trim\(\) \}\)/);
  assert.match(b, /catch \(e\) \{\s*if \(wz !== mine\) return;\s*setBusy\(form, false\);\s*showError\(form, spaceErrKey\(e\?\.code\), spaceErrField\(e\?\.code\)\);\s*return;\s*\}/);
  assert.doesNotMatch(b, /e\??\.key\b/);
  assert.match(b, /showError\(form, "spaceErrName", "name"\)/, "порожня назва — до запиту");
});

test("3c: «Довіритись…» на кроці 2 — deps.openTrust з простором майстра, потім loadStep2; app.js передає openTrust", () => {
  assert.match(fn(W, "click"), /else if \(a === "trust"\) trustFrom\(b\.dataset\.id\);/);
  const b = fn(W, "trustFrom");
  assert.match(b, /await deps\.openTrust\(e, mine\.spaceId\);/);
  assert.match(b, /if \(wz !== mine \|\| mine\.step !== 2\) return;/);
  assert.ok(b.indexOf("deps.openTrust(") < b.indexOf("loadStep2()"));
  assert.match(read("app.js"), /openTrust: \(entry, spaceId\) => openTrust\(entry, spaceId\),/);
});

test("3c: крок 3 — картки лише тим, хто не чекає довіри; невключений, що тепер потребує довіри, — назад на крок 2; untrusted — відмова без запиту", () => {
  const b = fn(W, "loadStep3");
  assert.match(b, /picked\.some\(\(e\) => needsTrust\(e\) && e\.enabled !== true\)/);
  assert.match(b, /mine\.cards = picked\.filter\(\(e\) => !needsTrust\(e\)\)\.map\(cardFrom\);/);
  assert.match(b, /mine\.waits = picked\.filter\(needsTrust\)\.map\(\(entry\) => \(\{ entry, result: null \}\)\);/);
  const r = fn(W, "runOp");
  assert.match(r, /else if \(op\.op === "untrusted"\)/);
  assert.ok(r.indexOf('op.op === "untrusted"') < r.indexOf("deps.post("), "відмова без запиту");
  assert.match(r, /for \(const w of mine\.waits\) if \(w\.entry\.id === op\.id\) w\.result = result;/);
});

test("3c: стан майстра й вʼю несуть `waits`; відмова в рядку «чекає довіри» стає ціллю фокуса після збійного проходу", () => {
  assert.match(fn(W, "open"), /waits: \[\]/);
  assert.match(fn(W, "view"), /waits: wz\.waits/);
  assert.match(fn(W, "loadStep3"), /mine\.waits = \[\];/, "скидається на початку loadStep3 разом із cards і offs");
  const b = fn(W, "submit3");
  assert.match(b, /\.wz-wait \.cn-res--err/);
  assert.match(b, /closest\("\.wz-card, \.wz-off, \.wz-wait"\)/);
});

test("крок 4, демо: submit4 шле /api/demo-task з простором майстра; радіо вмикає/вимикає назву й id", () => {
  const s4 = fn(W, "submit4");
  assert.match(s4, /mine\.s4\.source === "demo"/);
  assert.match(s4, /deps\.post\("\/api\/demo-task", \{ space: mine\.spaceId, title: t\("frDemoTaskTitle"\) \}\)/);
  assert.match(W, /for \(const sel of \["#tf-title", "#tf-id"\]\)/);
});

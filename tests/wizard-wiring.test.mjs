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
  assert.ok(b.indexOf("mine.checking = false") < b.indexOf("setBusy(form, true"), "прапорець знято до зайнятості (далі тримає wz.busy)");
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
  assert.match(fn(W, "submit1"), /deps\.afterSpaceEdited\(mine\.spaceId, saved\);\s*if \(wz !== mine\) return;/);
});

test("M4: «Назад» і «Закрити» перевіряють після питання, що майстер той самий", () => {
  assert.match(fn(W, "requestExit"), /const mine = wz;\s*if \(dirty\(\) && !\(await askDiscard\(\)\)\) return;\s*if \(wz !== mine\) return;/);
  assert.match(fn(W, "back"), /const mine = wz;\s*if \(wz\.step === 3 && dirty\(\) && !\(await askDiscard\(\)\)\) return;\s*if \(wz !== mine\) return;/);
});

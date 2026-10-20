import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const src = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

/** Тіло функції `name` (від `{` після сигнатури до парної `}`). */
function fn(name) {
  const m = new RegExp(`(?:async )?function ${name}\\(`).exec(src);
  assert.ok(m, `функції ${name} нема`);
  const open = src.indexOf("{", src.indexOf(")", m.index));
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) return src.slice(open, i + 1); }
  }
  throw new Error(`немає закриття для ${name}`);
}

/** Тіло функції без коментарів: пін дивиться на КОД, а не на пояснення між рядками (коментар не мусить ламати пін). */
const noComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<![:'"`])\/\/[^\n]*/g, "");
const fnc = (name) => noComments(fn(name));

test("дії смуги: conn веде на сторінку, логотип — завжди на «Задачі»", () => {
  assert.match(src, /\n  conn: \(\) => enterConnections\(\),/);
  assert.match(src, /\n  home: \(\) => enterHome\(\{ page: 'tasks' \}\),/);
  assert.match(fn("wireHome"), /case 'conn': enterConnections\(\); break;/);
});

test("enterHome тримає відкриту сторінку (перемикання простору й запис модулів лишають «Підключення»)", () => {
  const b = fn("enterHome");
  assert.match(b, /page \?\? \(was \? homePage : 'tasks'\)/);
  assert.match(b, /if \(homePage === 'conn'\)[\s\S]*?loadConn\(\{ spaces \}\)/);
  assert.match(b, /if \(next !== 'conn'\) closeCnDrawer\(\{ focus: false \}\)/);
});

test("barState і paletteState несуть homePage", () => {
  assert.match(src, /homePage: homeOpen \? homePage : null,/);
  assert.match(src, /homePage: st\.homePage,/);
});

test("клавіші сторінки «Задачі» на «Підключенні» не діють", () => {
  assert.match(src, /if \(!homeOpen \|\| ev\.isComposing \|\| paletteOverlay \|\| document\.querySelector\('\.cv-ask-scrim'\)\) return;\n  if \(homePage === 'conn'\) return;/);
});

test("перечитування при поверненні у вікно: на «Підключенні» — loadConn", () => {
  assert.match(fn("refreshHomeOnReturn"), /homePage === 'conn' \? loadConn\(\) : loadHome\(\)/);
});

test("запити сторінки несуть явний space (агент міг перемкнути активний простір)", () => {
  assert.match(fn("loadConn"), /api\(`\/api\/modules\?space=\$\{encodeURIComponent\(sp\.id\)\}`\)/);
  assert.match(fn("connCheck"), /postForm\('\/api\/module-check', \{ space: connState\.spaceId, id: e\.id \}\)/);
  /* Запис «Вимкнути» іде у ЗНІМОК простору, взятий до питання (`const spaceId`), а не в `connState.spaceId` на момент відповіді. */
  assert.match(fn("connDisable"), /postForm\('\/api\/module-disable', \{ space: spaceId, id: e\.id \}\)/);
});

test("після вимкнення — afterModulesChange; він ЛЕГКИЙ: без afterSpaceChange (той скидає обрану ітерацію, фільтри, плашки)", () => {
  assert.match(fn("connDisable"), /await afterModulesChange\(\);/);
  const b = fnc("afterModulesChange");
  assert.doesNotMatch(b, /afterSpaceChange|resetSpaceState|resetPerTaskState|enterHome/, "простір не змінився — скидати нічого");
  assert.match(b, /^\{\s*frameStale = true;\s*await loadSpaces\(\);\s*const seq = connState\.seq;\s*await render\(\{ keepFrame: true \}\);\s*paintBar\(\);\s*if \(connOpen\(\) && connState\.seq === seq\) await loadConn\(\{ spaces: false \}\);\s*\}$/);
});

test("рамка: frameStale оголошено ОДИН раз поряд зі станом сторінки; leaveHome перезавантажує її одразу після render()", () => {
  assert.equal([...src.matchAll(/\blet frameStale\b/g)].length, 1);
  assert.ok(src.indexOf("let frameStale = false;") < src.indexOf("async function leaveHome("), "стан оголошено ДО leaveHome (TDZ)");
  assert.match(fnc("leaveHome"), /await render\(\);\s*if \(frameStale\) \{ frameStale = false; reloadFrame\(\); \}/);
  /* Позначає застарілою ТІЛЬКИ запис модулів; перевірка статусу (`connCheck`, `cnDrawerCheck`) рамку не чіпає. */
  assert.deepEqual([...src.matchAll(/frameStale = true;/g)].length, 1);
  assert.doesNotMatch(fnc("connCheck"), /frameStale/);
  assert.doesNotMatch(fnc("cnDrawerCheck"), /frameStale/);
});

test("фокус після перемальовки повертається і на кнопки карток (data-cn + data-id)", () => {
  /* Не голий підрядок `a.dataset.cn` (його задовольнило б і `a.dataset.cnX`): умова, дія в селекторі й `data-id`. */
  assert.match(fnc("focusKey"), /if \(a\.dataset\.cn\) \{\s*return `\[data-cn="\$\{a\.dataset\.cn\}"\]\$\{a\.dataset\.id != null \? `\[data-id="\$\{CSS\.escape\(a\.dataset\.id\)\}"\]` : ''\}`;/);
});

/* ── бічна панель (Task 7) ─────────────────────────────────────────────────────────────────────────── */

test("панель: заглушки Task 6 замінені справжніми функціями; `cnDrawer` оголошено ОДИН раз, поряд зі станом сторінки", () => {
  assert.doesNotMatch(src, /function closeCnDrawer\(\) \{\}/);
  assert.doesNotMatch(src, /function openCnDrawer\(\) \{\}/);
  assert.equal([...src.matchAll(/\blet cnDrawer\b/g)].length, 1, "`let cnDrawer` — рівно одне оголошення");
  assert.ok(src.indexOf("let cnDrawer = null;") < src.indexOf("function enterHome("), "стан оголошено ДО enterHome (TDZ)");
  assert.match(fnc("openCnDrawer"), /spaceId: connState\.spaceId/, "панель памʼятає простір, для якого відкрита");
  assert.match(fnc("openCnDrawer"), /busy: false/);
});

test("панель: запис іде в простір, відкритий у панелі; заміна — з replace після підтвердження", () => {
  const b = fnc("cnSubmit");
  assert.match(b, /missingRequired\(cnDrawer\.fields, cur\)/);
  /* Не лише виклик: умова `if (miss.length)`, помилки полів, перемальовка й ВИХІД — ДО запиту (`if (false)` лишив би виклик). */
  assert.match(b, /const miss = missingRequired\(cnDrawer\.fields, cur\);\s*if \(miss\.length\) \{[\s\S]*?cnDrawer\.errors = Object\.fromEntries\(miss\.map\(\(k\) => \[k, 'cnFieldRequired'\]\)\);[\s\S]*?paintCnDrawer\(\);[\s\S]*?return;\s*\}/);
  assert.ok(b.indexOf("missingRequired(") < b.indexOf("postForm("), "обовʼязкові перевіряються ДО запиту");
  assert.match(b, /roleHolders\(cnDrawer\.entry, connState\.list\)/);
  assert.match(b, /t\('cnReplaceAsk', /);
  assert.match(b, /askYesNo\(q, \{ yes: t\('cnReplace'\) \}\)/);
  assert.match(b, /writePayload\(mine\.spaceId, mine\.id, patch, replace\)/);
  assert.match(b, /postForm\(mine\.mode === 'enable' \? '\/api\/module-enable' : '\/api\/module-settings', body\)/);
  assert.match(b, /await afterModulesChange\(\);/);
});

test("панель: `replace = true` стоїть ПІСЛЯ «так» у питанні й після перевірки, що панель та сама (без цього заміна — 409)", () => {
  /* Голий `writePayload(…, replace)` лишався б зеленим і без цього рядка: змінна була б завжди `false`. */
  assert.match(fnc("cnSubmit"),
    /if \(!\(await askYesNo\(q, \{ yes: t\('cnReplace'\) \}\)\)\) return;\s*if \(cnDrawer !== mine\) return;\s*replace = true;/);
  assert.match(fnc("cnSubmit"), /let replace = false;/);
});

test("панель: зайнятість — 'save' у записі, 'check' у перевірці, ніколи просто true", () => {
  assert.match(fnc("cnSubmit"), /mine\.busy = 'save'/);
  assert.match(fnc("cnDrawerCheck"), /mine\.busy = 'check'/);
  assert.doesNotMatch(src, /\b(?:mine|cnDrawer)\.busy = true\b/, "`busy` — вид зайнятості, а не прапорець: розмітка підписує кнопки за видом");
  assert.match(fnc("syncCnDrawer"), /submit\.disabled = !!cnDrawer\.busy \|\|/);
  assert.match(fnc("syncCnDrawer"), /check\.disabled = !!cnDrawer\.busy \|\| dirty/);
});

test("панель: секрети НЕ лишаються у формі після відповіді — у стані лише значення без секретів", () => {
  const b = fnc("cnSubmit");
  assert.match(b, /mine\.form = \{ values: cur\.values, secrets: \{\}, erase: cur\.erase \};/);
  /* І на шляху «обовʼязкове порожнє» (перемальовка панелі), і після відмови, і в перевірці, і при зміні мови. */
  assert.match(b, /cnDrawer\.form = \{ values: cur\.values, secrets: \{\}, erase: cur\.erase \};/);
  assert.match(fnc("cnDrawerCheck"), /mine\.form = \{ \.\.\.readCnForm\(cnDrawerNode\(\)\), secrets: \{\} \};/);
  /* Після відповіді з `ok: false` форма береться З ЗАПИСУ СЕРВЕРА (`initialForm`: секретів нема ніколи). */
  assert.match(b, /const entry = r\?\.module \?\? mine\.entry;\s*const fields = formFields\(entry\);\s*const init = initialForm\(fields\);/);
  assert.match(b, /form: init,/);
  /* Жодної копії введеного секрету у стан: ні `cur.secrets`, ні `.secrets` з читання DOM. */
  assert.doesNotMatch(src, /secrets: (?:cur|form|c)\.secrets/);
  /* Введені секрети ЧИТАЮТЬСЯ лише передачею `cur` у `formPatch`/`missingRequired`; жодного `.secrets` у запису й перевірці
     (під будь-яким іменем властивості стану — `secretsKept: cur.secrets` теж не проходить). */
  assert.doesNotMatch(b.replace("restoreCnSecrets(cur.secrets);", ""), /\.secrets\b/,
    "єдине місце, де cnSubmit торкається введених секретів, — повернення їх у поля ВЛАСТИВІСТЮ `.value`");
  assert.doesNotMatch(fnc("cnDrawerCheck"), /\.secrets\b/);
  assert.doesNotMatch(src, /\.form = \{[^}]*secrets: (?!\{\})/);
});

test("панель: перевірка в панелі — module-check простору панелі", () => {
  assert.match(fnc("cnDrawerCheck"), /postForm\('\/api\/module-check', \{ space: mine\.spaceId, id: mine\.id \}\)/);
  assert.match(fnc("cnDrawerCheck"), /if \(!cnDrawer \|\| cnDrawer\.busy\) return;/);
});

test("панель: Esc — запит закриття (з питанням при незбереженому), не під діалогом і не під палітрою", () => {
  assert.match(src, /document\.addEventListener\('keydown', \(ev\) => \{\n  if \(ev\.key === 'Escape' && cnDrawer && !paletteOverlay && !document\.querySelector\('\.cv-ask-scrim'\)\) \{\n    ev\.preventDefault\(\);\n    requestCloseCnDrawer\(\);\n  \}\n\}\);/);
  const b = fnc("requestCloseCnDrawer");
  assert.match(b, /if \(!cnDrawer \|\| cnDrawer\.busy\) return;/, "під час запиту панель не закривається");
  assert.match(b, /const dirty = isDirty\(formPatch\(mine\.fields, mine\.init, readCnForm\(cnDrawerNode\(\)\)\)\);/);
  assert.match(b, /if \(dirty && !\(await askYesNo\(t\('cnDiscardAsk'\), \{ yes: t\('cnDiscard'\), danger: true \}\)\)\) return;/);
  assert.match(b, /if \(cnDrawer === mine\) closeCnDrawer\(\);/, "після питання панель могла вже змінитись");
});

test("панель: «Стерти» — підпис СТАЛИЙ; міняє лише aria-pressed, примітку й aria-describedby поля, далі syncCnDrawer", () => {
  const b = fnc("toggleCnErase");
  assert.doesNotMatch(b, /textContent|innerHTML|innerText/, "підпис кнопки не чіпаємо — стан у aria-pressed і примітці");
  assert.match(b, /setAttribute\('aria-pressed', String\(on\)\)/);
  assert.match(b, /note\.hidden = !on;/);
  assert.match(b, /\[data-cn-field="\$\{CSS\.escape\(key\)\}"\]/, "поле — за ключем, а не за порядком");
  assert.match(b, /getAttribute\('aria-describedby'\)/);
  assert.match(b, /setAttribute\('aria-describedby', ids\.join\(' '\)\)/);
  assert.match(b, /filter\(\(x\) => x && x !== note\.id\)/, "чужі id (-state, -err) лишаються, наш знімається");
  assert.match(b, /ids\.splice\(/, "додається лише коли позначено");
  assert.match(b, /syncCnDrawer\(\);\s*\}$/);
});

test("панель: простір змінився — панель закривається без питання (loadConn, гілка зміни простору)", () => {
  assert.match(fnc("loadConn"),
    /if \(sp\.id !== connState\.spaceId\) \{\s*(?:\/\*[\s\S]*?\*\/\s*)?closeCnDrawer\(\{ focus: false \}\);\s*connState\.spaceId = sp\.id;/);
});

test("панель: закриття вертає фокус на кнопку картки, що відкрила її (запасний — будь-яка кнопка тієї ж картки)", () => {
  const b = fnc("closeCnDrawer");
  assert.match(b, /if \(!cnDrawer\) return;/);
  assert.match(b, /\[data-cn="\$\{op\.act\}"\]\[data-id="\$\{id\}"\]/);
  assert.match(b, /\[data-cn\]\[data-id="\$\{id\}"\]/);
});

test("мова: відкрита панель перемальовується разом з екраном", () => {
  assert.match(fnc("switchLang"), /if \(cnDrawer && !cnDrawer\.busy\) \{ cnDrawer\.form = \{ \.\.\.readCnForm\(cnDrawerNode\(\)\), secrets: \{\} \}; paintCnDrawer\(\); \}/);
});

test("фокус: кнопка картки зникла після перемальовки (дія змінилась) — фокус на іншу кнопку ТІЄЇ Ж картки, а не в нікуди", () => {
  const b = fnc("keepFocus");
  assert.match(b, /if \(!n\) \{[\s\S]*?if \(a\.dataset\?\.cn && a\.dataset\.id != null\) \{\s*root\.querySelector\(`\[data-cn\]\[data-id="\$\{CSS\.escape\(a\.dataset\.id\)\}"\]`\)\?\.focus\(\{ preventScroll: true \}\);\s*\}\s*return;\s*\}/);
});

/* ── знімок простору перед питанням (ревʼю Task 6, критичне) ──────────────────────────────────────────── */

test("connDisable: простір береться ДО питання, після відповіді сторінка мусить показувати той самий — інакше нічого не пишемо", () => {
  const b = fnc("connDisable");
  const iAsk = b.indexOf("askYesNo(");
  assert.ok(iAsk > 0);
  assert.match(b, /const spaceId = connState\.spaceId;/);
  assert.ok(b.indexOf("const spaceId = connState.spaceId;") < iAsk, "знімок id — ДО питання");
  assert.match(b, /const sp = connSpace\(\);/);
  assert.ok(b.indexOf("const sp = connSpace();") < iAsk, "запис простору для наслідків — теж ДО питання");
  assert.doesNotMatch(b, /currentSpace\(/, "наслідки лічимо за простором сторінки, а не за «поточним зараз»");
  assert.match(b, /if \(!\(await askYesNo\(\[t\('cnDisableAsk', modName\(e\)\), \.\.\.lines\]\.join\('\\n\\n'\), \{ yes: t\('cnDisable'\), danger: true \}\)\)\) return;\s*if \(!connOpen\(\) \|\| connState\.spaceId !== spaceId\) return;\s*connState\.busy\.set\(e\.id, 'disable'\);/);
  /* Після питання `connState.spaceId` читається ЛИШЕ для звірки зі знімком (`!== spaceId` перед записом, `=== spaceId`
     перед поверненням фокуса); у запит іде знімок. */
  assert.equal([...b.slice(iAsk).matchAll(/connState\.spaceId(?! [!=]== spaceId)/g)].length, 0);
  assert.equal([...b.slice(iAsk).matchAll(/connState\.spaceId !== spaceId/g)].length, 1);
});

test("сторінка малює простір connState.spaceId, а не «поточний зараз» (spacesResp міг змінитись від дропдауна чи ⌘K)", () => {
  assert.match(src, /const connSpace = \(\) => \(connState\.spaceId == null\s*\? currentSpace\(spacesResp\)\s*: \(Array\.isArray\(spacesResp\?\.spaces\) \? spacesResp\.spaces : \[\]\)\.find\(\(x\) => x\.id === connState\.spaceId\) \?\? null\);/);
  assert.match(src, /const connView = \(\) => \(\{ space: connSpace\(\), list: connState\.list,/);
  /* Свіжий вхід забуває простір попереднього візиту: «вантаження» малює заголовок поточного, а не давнього. */
  assert.match(fnc("enterHome"), /if \(fresh\) \{ connState\.spaceId = null; connState\.list = null; connState\.failed = null; connFocusPending = true; \}/);
});

test("cnSubmit: питання «Замінити?» стоїть між читанням простору й записом — запис іде у mine.spaceId, а після питання панель мусить бути та сама", () => {
  const b = fnc("cnSubmit");
  assert.match(b, /const mine = cnDrawer;/);
  assert.match(b, /if \(!\(await askYesNo\(q, \{ yes: t\('cnReplace'\) \}\)\)\) return;\s*if \(cnDrawer !== mine\) return;/);
  assert.match(b, /writePayload\(mine\.spaceId,/);
  assert.doesNotMatch(b, /connState\.spaceId|currentSpace\(|spaceNow\(/, "простір запису — лише знімок панелі");
});

/* ── фокус після картки (ревʼю Task 6) ─────────────────────────────────────────────────────────────── */

test("фокус: після «Перевірити» й «Вимкнути» кнопка картки відновлюється, коли фокус пропав (busy-перемальовка вимикає натиснуту кнопку)", () => {
  const h = fnc("refocusCard");
  assert.match(h, /if \(\(a && a !== document\.body && a\.isConnected\) \|\| paletteOverlay \|\| document\.querySelector\('\.cv-ask-scrim'\)\) return;/,
    "не краде фокус у того, хто вже деінде, і з-під палітри чи діалогу");
  assert.match(h, /\[data-cn="\$\{act\}"\]\[data-id="\$\{sel\}"\]:not\(\[disabled\]\)/, "спершу та сама дія");
  assert.match(h, /\[data-cn\]\[data-id="\$\{sel\}"\]:not\(\[disabled\]\)/, "запасна — будь-яка кнопка тієї ж картки");
  assert.match(fnc("connCheck"), /await loadConn\(\);\s*if \(connOpen\(\) && connState\.spaceId === spaceId\) refocusCard\(e\.id, 'check'\);/);
  assert.match(fnc("connDisable"), /finally \{[\s\S]*?refocusCard\(e\.id, 'disable'\);[\s\S]*?\}/);
});

/* ── сторінка як система: охоронці стану (ревʼю Task 6: 12 із 13 мутацій виживали) ─────────────────────────── */

test("loadConn: трійка охоронців застарілої відповіді (seq + connOpen) стоїть після КОЖНОГО await", () => {
  const b = fnc("loadConn");
  assert.match(b, /const seq = \+\+connState\.seq;/, "кожен виклик відкидає попередні");
  assert.match(b, /await loadSpaces\(\);\s*if \(seq !== connState\.seq \|\| !connOpen\(\)\) return;\s*paintBar\(\);/);
  assert.match(b, /const r = await api\(`\/api\/modules\?space=\$\{encodeURIComponent\(sp\.id\)\}`\);\s*if \(seq !== connState\.seq \|\| !connOpen\(\)\) return;\s*connState\.list = /);
  assert.match(b, /\} catch \(e\) \{\s*if \(seq !== connState\.seq \|\| !connOpen\(\)\) return;\s*connState\.failed = /);
  assert.equal([...b.matchAll(/seq !== connState\.seq \|\| !connOpen\(\)/g)].length, 3, "рівно три охоронці");
});

test("loadConn: `spaces` вирішує, чи перечитувати простори; простору не стало — «Задачі»; зміна простору чистить усе пер-просторове", () => {
  const b = fnc("loadConn");
  assert.match(b, /if \(spaces\) \{\s*await loadSpaces\(\);/);
  assert.match(b, /const sp = currentSpace\(spacesResp\);\s*if \(!sp\) \{ enterHome\(\{ page: 'tasks' \}\); return; \}/);
  assert.match(b, /if \(sp\.id !== connState\.spaceId\) \{[\s\S]*?closeCnDrawer\(\{ focus: false \}\);\s*connState\.spaceId = sp\.id; connState\.list = null; connState\.failed = null; connState\.busy\.clear\(\);\s*paintHome\(\);\s*\}/);
});

test("connAction: дія над модулем, що вже в польоті, ігнорується; кожна дія веде у свою функцію", () => {
  const b = fnc("connAction");
  assert.match(b, /if \(act === 'retry'\) \{ loadConn\(\); return; \}/);
  assert.match(b, /const e = \(connState\.list \|\| \[\]\)\.find\(\(x\) => x\.id === id\);\s*if \(!e \|\| connState\.busy\.has\(id\)\) return;/);
  assert.match(b, /if \(act === 'enable'\) openCnDrawer\(e, 'enable'\);\s*else if \(act === 'configure'\) openCnDrawer\(e, 'edit'\);\s*else if \(act === 'check'\) connCheck\(e\);\s*else if \(act === 'disable'\) connDisable\(e\);/);
});

test("зайнятість картки: ставиться ДО запиту й знімається в finally/catch; «Вимкнути» знімає її лише коли свіжий список уже прийшов", () => {
  const c = fnc("connCheck");
  assert.match(c, /connState\.busy\.set\(e\.id, 'check'\); paintHome\(\);\s*try \{ await postForm\(/);
  assert.match(c, /finally \{ connState\.busy\.delete\(e\.id\); \}\s*await loadConn\(\);/);
  const d = fnc("connDisable");
  assert.match(d, /connState\.busy\.set\(e\.id, 'disable'\); paintHome\(\);\s*try \{ await postForm\(/);
  assert.match(d, /catch \(err\) \{\s*connState\.busy\.delete\(e\.id\); paintHome\(\);[\s\S]*?return;\s*\}/, "відмова: знімаємо одразу");
  assert.match(d, /try \{ await afterModulesChange\(\); \}\s*finally \{\s*connState\.busy\.delete\(e\.id\); paintHome\(\);/, "успіх: знімаємо ПІСЛЯ перечитування");
  assert.ok(d.indexOf("await afterModulesChange()") < d.lastIndexOf("connState.busy.delete(e.id)"), "delete — після await перечитування");
});

test("вихід і вхід: leaveHome закриває панель; enterHome різнить свіжий вхід, скасовує запізнілий loadHome і передає `spaces` далі", () => {
  assert.match(fnc("leaveHome"), /^\{\s*closeCnDrawer\(\{ focus: false \}\);/);
  const b = fnc("enterHome");
  assert.match(b, /const fresh = !was \|\| next !== homePage;\s*homePage = next;/);
  assert.match(b, /if \(homePage === 'conn'\) \{\s*homeSeq \+= 1;\s*if \(fresh\) \{ connState\.spaceId = null;/, "запізнілий loadHome задач не перемальовує «Підключення»");
  assert.match(b, /paintHome\(\);\s*loadConn\(\{ spaces \}\);\s*return;/);
});

test("wireHome: клік по [data-cn] (картка, помилка сторінки) іде в connAction і ДО обробки [data-th]", () => {
  const b = fnc("wireHome");
  const iC = b.indexOf("const c = ev.target.closest('[data-cn]');");
  assert.ok(iC > 0);
  assert.match(b, /const c = ev\.target\.closest\('\[data-cn\]'\);\s*if \(c\) \{ connAction\(c\.dataset\.cn, c\.dataset\.id\); return; \}/);
  assert.ok(iC < b.indexOf("const b = ev.target.closest('[data-th]');"), "делегація data-cn — раніше за data-th");
});

test("перший фокус після списку не краде фокус у палітри чи діалогу", () => {
  assert.match(fnc("loadConn"),
    /if \(connFocusPending\) \{\s*connFocusPending = false;\s*if \(!paletteOverlay && !document\.querySelector\('\.cv-ask-scrim'\)\) \{\s*homeNode\(\)\?\.querySelector\('\.cn-card \[data-cn\], \[data-cn="retry"\]'\)\?\.focus\(\{ preventScroll: true \}\);\s*\}\s*\}/);
});

test("cnSubmit: при невдалій перевірці обовʼязкових введені секрети повертаються в поля ВЛАСТИВІСТЮ `.value` (не розміткою, не станом)", () => {
  const b = fnc("cnSubmit");
  assert.match(b, /paintCnDrawer\(\);\s*restoreCnSecrets\(cur\.secrets\);\s*cnDrawerNode\(\)\.querySelector\('\[aria-invalid="true"\]'\)/, "після перемальовки, до фокуса на помилці");
  const h = fnc("restoreCnSecrets");
  assert.match(h, /\[data-cn-field="\$\{CSS\.escape\(k\)\}"\]\[data-type="secret"\]/, "лише поля паролів");
  assert.match(h, /if \(n && v\) n\.value = v;/);
  assert.match(h, /syncCnDrawer\(\);/, "кнопки залежать від введеного");
  assert.doesNotMatch(h, /setAttribute|innerHTML|outerHTML|insertAdjacent|drawerHTML|cnDrawer\./, "секрет — лише властивість, ні розмітка, ні стан");
  /* Стан по-старому без секретів. */
  assert.match(b, /cnDrawer\.form = \{ values: cur\.values, secrets: \{\}, erase: cur\.erase \};\s*cnDrawer\.errors/);
});

test("рамка: render({ keepFrame }) не переприсвоює frame.src (кожне присвоєння — перезавантаження); лише afterModulesChange його вмикає", () => {
  assert.match(src, /async function render\(\{ keepFrame = false \} = \{\}\) \{/);
  assert.match(fnc("render"), /applyMode\(task, \{ keepFrame \}\);/);
  assert.match(fnc("applyMode"), /if \(!keepFrame\) \{\s*frame\.src = /);
  assert.match(src, /function applyMode\(task, \{ keepFrame = false \} = \{\}\) \{/);
  /* Єдине місце, що тримає рамку: легкий шлях після запису модулів. Усі інші `render()` — з перезавантаженням. */
  assert.deepEqual([...src.matchAll(/render\(\{ keepFrame: true \}\)/g)].length, 1);
  assert.match(fnc("afterModulesChange"), /await render\(\{ keepFrame: true \}\);/);
});

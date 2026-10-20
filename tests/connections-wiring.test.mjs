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
  assert.match(fn("connDisable"), /postForm\('\/api\/module-disable', \{ space: connState\.spaceId, id: e\.id \}\)/);
});

test("після вимкнення — afterModulesChange (= afterSpaceChange: смуга, рамка, інспектор)", () => {
  assert.match(fn("connDisable"), /await afterModulesChange\(\);/);
  assert.match(fn("afterModulesChange"), /await afterSpaceChange\(\);/);
});

test("фокус після перемальовки повертається і на кнопки карток (data-cn + data-id)", () => {
  /* Не голий підрядок `a.dataset.cn` (його задовольнило б і `a.dataset.cnX`): умова, дія в селекторі й `data-id`. */
  assert.match(fn("focusKey"), /if \(a\.dataset\.cn\) \{\s*return `\[data-cn="\$\{a\.dataset\.cn\}"\]\$\{a\.dataset\.id != null \? `\[data-id="\$\{CSS\.escape\(a\.dataset\.id\)\}"\]` : ''\}`;/);
});

/* ── бічна панель (Task 7) ─────────────────────────────────────────────────────────────────────────── */

test("панель: заглушки Task 6 замінені справжніми функціями; `cnDrawer` оголошено ОДИН раз, поряд зі станом сторінки", () => {
  assert.doesNotMatch(src, /function closeCnDrawer\(\) \{\}/);
  assert.doesNotMatch(src, /function openCnDrawer\(\) \{\}/);
  assert.equal([...src.matchAll(/\blet cnDrawer\b/g)].length, 1, "`let cnDrawer` — рівно одне оголошення");
  assert.ok(src.indexOf("let cnDrawer = null;") < src.indexOf("function enterHome("), "стан оголошено ДО enterHome (TDZ)");
  assert.match(fn("openCnDrawer"), /spaceId: connState\.spaceId/, "панель памʼятає простір, для якого відкрита");
  assert.match(fn("openCnDrawer"), /busy: false/);
});

test("панель: запис іде в простір, відкритий у панелі; заміна — з replace після підтвердження", () => {
  const b = fn("cnSubmit");
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
  assert.match(fn("cnSubmit"),
    /if \(!\(await askYesNo\(q, \{ yes: t\('cnReplace'\) \}\)\)\) return;\s*if \(cnDrawer !== mine\) return;\s*replace = true;/);
  assert.match(fn("cnSubmit"), /let replace = false;/);
});

test("панель: зайнятість — 'save' у записі, 'check' у перевірці, ніколи просто true", () => {
  assert.match(fn("cnSubmit"), /mine\.busy = 'save'/);
  assert.match(fn("cnDrawerCheck"), /mine\.busy = 'check'/);
  assert.doesNotMatch(src, /\b(?:mine|cnDrawer)\.busy = true\b/, "`busy` — вид зайнятості, а не прапорець: розмітка підписує кнопки за видом");
  assert.match(fn("syncCnDrawer"), /submit\.disabled = !!cnDrawer\.busy \|\|/);
  assert.match(fn("syncCnDrawer"), /check\.disabled = !!cnDrawer\.busy \|\| dirty/);
});

test("панель: секрети НЕ лишаються у формі після відповіді — у стані лише значення без секретів", () => {
  const b = fn("cnSubmit");
  assert.match(b, /mine\.form = \{ values: cur\.values, secrets: \{\}, erase: cur\.erase \};/);
  /* І на шляху «обовʼязкове порожнє» (перемальовка панелі), і після відмови, і в перевірці, і при зміні мови. */
  assert.match(b, /cnDrawer\.form = \{ values: cur\.values, secrets: \{\}, erase: cur\.erase \};/);
  assert.match(fn("cnDrawerCheck"), /mine\.form = \{ \.\.\.readCnForm\(cnDrawerNode\(\)\), secrets: \{\} \};/);
  /* Після відповіді з `ok: false` форма береться З ЗАПИСУ СЕРВЕРА (`initialForm`: секретів нема ніколи). */
  assert.match(b, /const entry = r\?\.module \?\? mine\.entry;\s*const fields = formFields\(entry\);\s*const init = initialForm\(fields\);/);
  assert.match(b, /form: init,/);
  /* Жодної копії введеного секрету у стан: ні `cur.secrets`, ні `.secrets` з читання DOM. */
  assert.doesNotMatch(src, /secrets: (?:cur|form|c)\.secrets/);
  /* Введені секрети ЧИТАЮТЬСЯ лише передачею `cur` у `formPatch`/`missingRequired`; жодного `.secrets` у запису й перевірці
     (під будь-яким іменем властивості стану — `secretsKept: cur.secrets` теж не проходить). */
  assert.doesNotMatch(b, /\.secrets\b/);
  assert.doesNotMatch(fn("cnDrawerCheck"), /\.secrets\b/);
  assert.doesNotMatch(src, /\.form = \{[^}]*secrets: (?!\{\})/);
});

test("панель: перевірка в панелі — module-check простору панелі", () => {
  assert.match(fn("cnDrawerCheck"), /postForm\('\/api\/module-check', \{ space: mine\.spaceId, id: mine\.id \}\)/);
  assert.match(fn("cnDrawerCheck"), /if \(!cnDrawer \|\| cnDrawer\.busy\) return;/);
});

test("панель: Esc — запит закриття (з питанням при незбереженому), не під діалогом і не під палітрою", () => {
  assert.match(src, /document\.addEventListener\('keydown', \(ev\) => \{\n  if \(ev\.key === 'Escape' && cnDrawer && !paletteOverlay && !document\.querySelector\('\.cv-ask-scrim'\)\) \{\n    ev\.preventDefault\(\);\n    requestCloseCnDrawer\(\);\n  \}\n\}\);/);
  const b = fn("requestCloseCnDrawer");
  assert.match(b, /if \(!cnDrawer \|\| cnDrawer\.busy\) return;/, "під час запиту панель не закривається");
  assert.match(b, /const dirty = isDirty\(formPatch\(mine\.fields, mine\.init, readCnForm\(cnDrawerNode\(\)\)\)\);/);
  assert.match(b, /if \(dirty && !\(await askYesNo\(t\('cnDiscardAsk'\), \{ yes: t\('cnDiscard'\), danger: true \}\)\)\) return;/);
  assert.match(b, /if \(cnDrawer === mine\) closeCnDrawer\(\);/, "після питання панель могла вже змінитись");
});

test("панель: «Стерти» — підпис СТАЛИЙ; міняє лише aria-pressed, примітку й aria-describedby поля, далі syncCnDrawer", () => {
  const b = fn("toggleCnErase");
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
  assert.match(fn("loadConn"),
    /if \(sp\.id !== connState\.spaceId\) \{\s*(?:\/\*[\s\S]*?\*\/\s*)?closeCnDrawer\(\{ focus: false \}\);\s*connState\.spaceId = sp\.id;/);
});

test("панель: закриття вертає фокус на кнопку картки, що відкрила її (запасний — будь-яка кнопка тієї ж картки)", () => {
  const b = fn("closeCnDrawer");
  assert.match(b, /if \(!cnDrawer\) return;/);
  assert.match(b, /\[data-cn="\$\{op\.act\}"\]\[data-id="\$\{id\}"\]/);
  assert.match(b, /\[data-cn\]\[data-id="\$\{id\}"\]/);
});

test("мова: відкрита панель перемальовується разом з екраном", () => {
  assert.match(fn("switchLang"), /if \(cnDrawer && !cnDrawer\.busy\) \{ cnDrawer\.form = \{ \.\.\.readCnForm\(cnDrawerNode\(\)\), secrets: \{\} \}; paintCnDrawer\(\); \}/);
});

test("фокус: кнопка картки зникла після перемальовки (дія змінилась) — фокус на іншу кнопку ТІЄЇ Ж картки, а не в нікуди", () => {
  const b = fn("keepFocus");
  assert.match(b, /if \(!n\) \{[\s\S]*?if \(a\.dataset\?\.cn && a\.dataset\.id != null\) \{\s*root\.querySelector\(`\[data-cn\]\[data-id="\$\{CSS\.escape\(a\.dataset\.id\)\}"\]`\)\?\.focus\(\{ preventScroll: true \}\);\s*\}\s*return;\s*\}/);
});

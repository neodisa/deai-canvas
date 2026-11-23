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
  assert.match(src, /\n  conn: \(\) => \{ setConnSec\('mods'\); enterConnections\(\); \},/);
  assert.match(src, /\n  home: async \(\) => \{ if \(homeOpen && homePage === 'wiz'\) \{ await wiz\.requestExit\(\); return; \} if \(cnDrawer && !\(await dismissCnDrawer\(\)\)\) return; enterHome\(\{ page: 'tasks' \}\); \},/);
  assert.match(fn("wireHome"), /case 'conn': setConnSec\('mods'\); enterConnections\(\); break;/);
});

test("логотип і «назад до задачі» не гублять брудну панель мовчки: через dismissCnDrawer, а без панелі — синхронно, як було", () => {
  /* Умова `cnDrawer &&` ПЕРЕД `await`: без панелі дія виконується в тому ж такті (жодного зайвого мікрозавдання). */
  assert.doesNotMatch(src, /\n  back: async/, "дія back прибрана: назад до задачі — вкладка");
  assert.match(src, /\n  home: async \(\) => \{ if \(homeOpen && homePage === 'wiz'\) \{ await wiz\.requestExit\(\); return; \} if \(cnDrawer && !\(await dismissCnDrawer\(\)\)\) return; enterHome\(\{ page: 'tasks' \}\); \},/);
  const b = fnc("dismissCnDrawer");
  assert.match(b, /^\{\s*if \(!cnDrawer\) return true;\s*if \(cnDrawer\.busy\) return false;\s*await requestCloseCnDrawer\(\);\s*return !cnDrawer;\s*\}$/,
    "нема панелі — true; запит у польоті — false (ігнор); інакше закриття з питанням, і true лише коли панель справді зникла");
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

test("клавіші сторінки «Задачі» на «Підключенні» й майстрі не діють", () => {
  assert.match(src, /if \(!homeOpen \|\| ev\.isComposing \|\| paletteOverlay \|\| askUp\(\)\) return;\n  if \(homePage !== 'tasks'\) return;/);
});

test("перечитування при поверненні у вікно: на «Підключенні» — loadConn", () => {
  assert.match(fn("refreshHomeOnReturn"), /homePage === 'conn' \? loadConn\(\) : loadHome\(\)/);
});

test("запити сторінки несуть явний space (агент міг перемкнути активний простір)", () => {
  assert.match(fn("loadConn"), /api\(`\/api\/modules\?space=\$\{encodeURIComponent\(sp\.id\)\}`\)/);
  assert.match(fn("connCheck"), /checkPost\('\/api\/module-check', \{ space: connState\.spaceId, id: e\.id \}, e\)/);
  /* Запис «Вимкнути» іде у ЗНІМОК простору, взятий до питання (`const spaceId`), а не в `connState.spaceId` на момент відповіді. */
  assert.match(fn("connDisable"), /postForm\('\/api\/module-disable', \{ space: spaceId, id: e\.id \}\)/);
});

test("після вимкнення — afterModulesChange; він ЛЕГКИЙ: без afterSpaceChange (той скидає обрану ітерацію, фільтри, плашки)", () => {
  assert.match(fn("connDisable"), /await afterModulesChange\(\);/);
  const b = fnc("afterModulesChange");
  assert.doesNotMatch(b, /afterSpaceChange|resetSpaceState|resetPerTaskState|enterHome/, "простір не змінився — скидати нічого");
  assert.match(b, /^\{\s*ovc\.invalidate\(\);\s*await loadSpaces\(\);\s*const seq = connState\.seq;\s*await render\(\{ keepFrame: homeOpen \}\);\s*await refreshGitlab\(\);\s*paintBar\(\);\s*await loadModExt\(\);\s*if \(connOpen\(\) && connState\.seq === seq\) await loadConn\(\{ spaces: false \}\);\s*\}$/);
});

test("afterModulesChange ПЕРШИМ інвалідує коментатор «Огляду» (інакше нові піни йдуть у сервіс, з якого людина щойно пішла)", () => {
  const b = fnc("afterModulesChange");
  assert.ok(/^\{\s*ovc\.invalidate\(\);/.test(b), "ovc.invalidate() — перший рядок тіла: раніше за loadSpaces і render()");
  assert.ok(b.indexOf("ovc.invalidate()") < b.indexOf("render("), "invalidate раніше за render(): той у режимі «Огляд» кличе ovc.enter()");
  /* Саме `invalidate` коментатора, а не `leave`/`rebuild`: ті ключ «ітерація|канал» не скидають. */
  assert.equal([...src.matchAll(/ovc\.invalidate\(\)/g)].length, 1, "єдине місце — afterModulesChange (іншим шляхам модулі не міняються)");
  const oc = readFileSync(new URL("../app/overview-comments.js", import.meta.url), "utf8");
  assert.match(oc, /invalidate\(\) \{\s*epoch \+= 1;\s*if \(cl\) \{ cl\.destroy\(\); cl = null; \}\s*subs\.length = 0; cfgKey = null; inflight = null;\s*\},/);
  /* Фабрики модулів лишаються: файли адаптера не змінюються, змінюється налаштування. */
  assert.doesNotMatch(oc.slice(oc.indexOf("invalidate() {"), oc.indexOf("invalidate() {") + 400), /FACTORIES/);
});

test("Esc панелі не спрацьовує під час IME-композиції (там Esc скасовує набране, а не закриває панель)", () => {
  assert.match(src, /if \(ev\.key === 'Escape' && !ev\.isComposing && !ev\.defaultPrevented && cnDrawer && /);
});

test("рамка: окремого reloadFrame після виходу нема — render() сам присвоює frame.src (інакше перезавантажувався СТАРИЙ документ, 404 у рамці)", () => {
  /* Ні стану `frameStale`, ні жодного його читання: рамку оновлює лише присвоєння `frame.src` у `render()`. */
  assert.doesNotMatch(src, /frameStale/, "frameStale не існує: рамку після виходу перезавантажує render()");
  const b = fnc("leaveHome");
  assert.doesNotMatch(b, /reloadFrame/, "після render() рамка не перезавантажується вдруге — location.reload() бере старий URL");
  assert.match(b, /\n  await render\(\);\n/, "render() на виході — єдине, що оновлює рамку");
  /* `reloadFrame` лишається лише для живого перезавантаження макета (опитування штампа і плашка «Оновити»). */
  assert.equal([...noComments(src).matchAll(/reloadFrame\(\)/g)].length, 3, "функція + дві дії штампа; leaveHome її не кличе");
  assert.doesNotMatch(fnc("connCheck"), /frameStale|reloadFrame/);
  assert.doesNotMatch(fnc("cnDrawerCheck"), /frameStale|reloadFrame/);
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
  assert.ok(b.indexOf("missingRequired(") < b.indexOf("checkPost("), "обовʼязкові перевіряються ДО запиту");
  /* Питання «Замінити?» і свіжа згода — у `cnConfirmReplace` (окремий пін нижче); тут лише передача рішення в запис. */
  assert.match(b, /const verdict = await cnConfirmReplace\(mine\);\s*if \(verdict === null\) return;\s*replace = verdict;/);
  assert.match(b, /writePayload\(mine\.spaceId, mine\.id, patch, replace\)/);
  assert.match(b, /checkPost\(mine\.mode === 'enable' \? '\/api\/module-enable' : '\/api\/module-settings', body, mine\.entry\)/);
  assert.match(b, /await afterModulesChange\(\);/);
});

test("згода на заміну СВІЖА: після «так» список перечитується; власники змінились — питаємо ще раз, вдруге — відмова «роль зайнята»", () => {
  const b = fnc("cnConfirmReplace");
  assert.match(b, /let holders = roleHolders\(mine\.entry, connState\.list\);\s*if \(!holders\.length\) return false;/, "ніхто не тримає роль — `replace` не потрібен");
  assert.match(b, /t\('cnReplaceAsk', roleTitle\(shared\[0\]\), holders\.map\(modName\)\.join\(', '\), modName\(mine\.entry\)\)/);
  /* «Ні» — нічого не пишемо; після відповіді панель мусить бути та сама. */
  assert.match(b, /const named = round === 0 && mine\.catalogHolders && sameHolders\(holders, mine\.catalogHolders\);\s*if \(!named && !\(await askYesNo\(q, \{ yes: t\('cnReplace'\) \}\)\)\) return null;\s*if \(cnDrawer !== mine\) return null;/);
  /* Перечитування — ПІСЛЯ питання, в простір панелі (не `connState.spaceId`), а відповідь не стирає введене. */
  assert.match(b, /formApi\(`\/api\/modules\?space=\$\{encodeURIComponent\(mine\.spaceId\)\}`\)/);
  assert.ok(b.indexOf("askYesNo(") < b.indexOf("formApi("), "список перечитується ПІСЛЯ «так», а не до питання");
  assert.match(b, /catch \(err\) \{\s*if \(cnDrawer === mine\) cnShowKept\(mine, \{ kind: 'refused', \.\.\.refusalView\(err\) \}\);\s*return null;\s*\}/, "не вдалось перечитати — відмова без запису");
  assert.match(b, /if \(cnDrawer !== mine\) return null;\s*if \(!Array\.isArray\(list\)\) list = \[\];\s*if \(connOpen\(\) && connState\.spaceId === mine\.spaceId\) \{ connState\.list = list; paintHome\(\); \}/,
    "свіжий список оновлює сторінку лише коли вона ще показує той самий простір");
  /* Рішення: ті самі власники — слати; змінились — ще раз; вдруге змінились — відмова; роль звільнилась — без `replace`. */
  assert.match(b, /const now = roleHolders\(mine\.entry, list\);\s*if \(sameHolders\(now, holders\)\) return true;\s*if \(!now\.length\) return false;\s*if \(round === 1\) \{ cnShowKept\(mine, \{ kind: 'refused', key: 'cnRefRoleTaken', detail: '' \}\); return null; \}\s*holders = now;/);
  assert.match(b, /finally \{ mine\.asking = false; \}/, "прапорець «питаємо» знімається за будь-якого виходу");
  /* Лише ТУТ народжується `replace: true`; у cnSubmit воно дорівнює вердикту. */
  assert.match(fnc("cnSubmit"), /let replace = false;/);
  assert.equal([...fnc("cnConfirmReplace").matchAll(/return true;/g)].length, 1, "єдиний шлях до `replace: true` — ті самі власники");
  assert.match(fnc("cnSubmit"), /if \(!cnDrawer \|\| cnDrawer\.busy \|\| cnDrawer\.asking\) return;/, "друге «Підключити» під питанням не стартує");
  /* Порівняння — за множиною id, без порядку. */
  assert.match(src, /const sameHolders = \(a, b\) => a\.length === b\.length && a\.every\(\(x\) => b\.some\(\(y\) => y\.id === x\.id\)\);/);
});

test("після заміни тост називає вимкнені модулі (cnToastReplaced з назвами зі списку, запасний — id)", () => {
  const b = fnc("cnSubmit");
  assert.match(b, /const off = cnReplacedNames\(r\);/);
  assert.match(b, /toast\(off \? t\('cnToastReplaced', name, off\) : t\(mine\.mode === 'enable' \? 'cnToastEnabled' : 'cnToastSaved', name\)\);/);
  const h = fnc("cnReplacedNames");
  assert.match(h, /Array\.isArray\(r\?\.replaced\) \? r\.replaced : \[\]/);
  assert.match(h, /return e \? modName\(e\) : String\(id\);/);
  /* Назви беруться ДО перечитування списку (`afterModulesChange`), інакше список уже свіжий — теж ок, але запасний id тоді зайвий. */
  assert.ok(b.indexOf("cnReplacedNames(r)") < b.indexOf("await afterModulesChange()"));
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
  assert.match(fnc("cnDrawerCheck"), /checkPost\('\/api\/module-check', \{ space: mine\.spaceId, id: mine\.id \}, mine\.entry\)/);
  assert.match(fnc("cnDrawerCheck"), /if \(!cnDrawer \|\| cnDrawer\.busy\) return;/);
});

test("панель: Esc — запит закриття (з питанням при незбереженому), не під діалогом і не під палітрою", () => {
  assert.match(src, /document\.addEventListener\('keydown', \(ev\) => \{\n  if \(ev\.key === 'Escape' && !ev\.isComposing && !ev\.defaultPrevented && cnDrawer && !paletteOverlay && !askUp\(\)\) \{\n    ev\.preventDefault\(\);\n    requestCloseCnDrawer\(\);\n  \}\n\}\);/);
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
  /* Введений секрет переживає перемальовку: знімок ДО, повернення ВЛАСТИВІСТЮ `.value` ПІСЛЯ (як при порожньому обовʼязковому). */
  assert.match(fnc("switchLang"), /if \(cnDrawer && !cnDrawer\.busy\) \{\s*const cur = readCnForm\(cnDrawerNode\(\)\);\s*cnDrawer\.form = \{ \.\.\.cur, secrets: \{\} \};\s*paintCnDrawer\(\);\s*restoreCnSecrets\(cur\.secrets\);\s*\}/);
});

test("фокус: кнопка картки зникла після перемальовки (дія змінилась) — фокус на іншу кнопку ТІЄЇ Ж картки, а не в нікуди", () => {
  const b = fnc("keepFocus");
  assert.match(b, /if \(!n\) \{[\s\S]*?if \(a\.dataset\?\.cn && a\.dataset\.id != null\) \{\s*root\.querySelector\(`\[data-cn\]\[data-id="\$\{CSS\.escape\(a\.dataset\.id\)\}"\]`\)\?\.focus\(\{ preventScroll: true \}\);\s*\}\s*return;\s*\}/);
});

/* ── знімок простору перед питанням (ревʼю Task 6, критичне) ──────────────────────────────────────────── */

test("«Вимкнути»: питання стоїть у картці (етап Е); запит іде у connState.spaceId; перехід в інший простір питання знімає", () => {
  /* Діалог `askYesNo` для картки більше не потрібен: питання — `.mc--ask` (`askConnDisable`), відповідь — `askyes`. */
  const b = fnc("connDisable");
  assert.doesNotMatch(b, /askYesNo\(/, "діалогу нема — питання вже було в картці");
  assert.match(b, /^\{\s*const spaceId = connState\.spaceId;\s*connAsk = null;\s*connState\.busy\.set\(e\.id, 'disable'\);/);
  assert.doesNotMatch(b, /currentSpace\(/, "простір запису — той, що малює сторінка, а не «поточний зараз»");
  assert.match(b, /postForm\('\/api\/module-disable', \{ space: spaceId, id: e\.id \}\)/);
  assert.equal([...b.matchAll(/connState\.spaceId(?! [!=]== spaceId)/g)].length, 1, "connState.spaceId читається лише для знімка на вході");
  /* Питання, відкрите в одному просторі, не переживає перехід в інший: `askyes` без питання (`connAsk.id`) нічого не робить. */
  assert.match(fnc("connAction"), /if \(act === 'askyes'\) \{ if \(connAsk\?\.id === id\) connDisable\(e\); return; \}/);
  assert.match(fnc("loadConn"), /connState\.busy\.clear\(\); connAsk = null;/);
  assert.match(fnc("askConnDisable"), /connAsk = \{ id: e\.id \};\s*paintHome\(\);\s*homeNode\(\)\?\.querySelector\(`\.mc--ask\[data-id="\$\{CSS\.escape\(e\.id\)\}"\] \.cfm-no`\)\?\.focus\(\{ preventScroll: true \}\);/,
    "фокус — на «Скасувати»");
  assert.match(fnc("cancelConnAsk"), /connAsk = null;\s*paintHome\(\);\s*if \(refocus\) refocusMore\(id\);/, "після скасування фокус — на «⋯» картки");
});

test("сторінка малює простір connState.spaceId, а не «поточний зараз» (spacesResp міг змінитись від дропдауна чи ⌘K)", () => {
  assert.match(src, /const connSpace = \(\) => \(connState\.spaceId == null\s*\? currentSpace\(spacesResp\)\s*: \(Array\.isArray\(spacesResp\?\.spaces\) \? spacesResp\.spaces : \[\]\)\.find\(\(x\) => x\.id === connState\.spaceId\) \?\? null\);/);
  assert.match(src, /const connView = \(\) => \(\{ space: connSpace\(\), list: connState\.list,/);
  /* Свіжий вхід забуває простір попереднього візиту: «вантаження» малює заголовок поточного, а не давнього. */
  assert.match(fnc("enterHome"), /if \(fresh\) \{ connState\.spaceId = null; connState\.list = null; connState\.failed = null; connFocusPending = true; connAsk = null; \}/);
});

test("cnSubmit: запис іде у mine.spaceId; після питання панель мусить бути та сама (інакше нічого не пишемо)", () => {
  const b = fnc("cnSubmit");
  assert.match(b, /const mine = cnDrawer;/);
  assert.match(fnc("cnConfirmReplace"), /const named = round === 0 && mine\.catalogHolders && sameHolders\(holders, mine\.catalogHolders\);\s*if \(!named && !\(await askYesNo\(q, \{ yes: t\('cnReplace'\) \}\)\)\) return null;\s*if \(cnDrawer !== mine\) return null;/);
  assert.match(b, /writePayload\(mine\.spaceId,/);
  assert.doesNotMatch(b, /connState\.spaceId|currentSpace\(|spaceNow\(/, "простір запису — лише знімок панелі");
  assert.doesNotMatch(fnc("cnConfirmReplace"), /currentSpace\(|spaceNow\(/);
});

/* ── фокус після картки (ревʼю Task 6) ─────────────────────────────────────────────────────────────── */

test("фокус: після «Перевірити» й «Вимкнути» кнопка картки відновлюється, коли фокус пропав (busy-перемальовка вимикає натиснуту кнопку)", () => {
  const h = fnc("refocusCard");
  assert.match(h, /if \(\(a && a !== document\.body && a\.isConnected\) \|\| paletteOverlay \|\| askUp\(\)\) return;/,
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
  assert.match(b, /if \(sp\.id !== connState\.spaceId\) \{[\s\S]*?closeCnDrawer\(\{ focus: false \}\);\s*connState\.spaceId = sp\.id; connState\.list = null; connState\.tools = null; connState\.notes = \[\]; connState\.authoring = ''; connState\.failed = null; connState\.busy\.clear\(\); connAsk = null;\s*paintHome\(\);\s*\}/);
});

test("3c: примітки своїх модулів — зі списку модулів у стан сторінки; зміна простору їх чистить", () => {
  assert.match(src, /const connState = \{ spaceId: null, list: null, tools: null, notes: \[\], authoring: '', failed: null, busy: new Map\(\), seq: 0 \};/);
  const b = fnc("loadConn");
  assert.match(b, /connState\.notes = Array\.isArray\(r\?\.notes\) \? r\.notes : \[\];/);
  assert.match(b, /connState\.authoring = typeof r\?\.deai\?\.authoring === 'string' \? r\.deai\.authoring : '';/, "шлях до інструкції агенту — з відповіді сервера");
  assert.match(b, /connState\.list = null; connState\.tools = null; connState\.notes = \[\];/, "інший простір — без чужих приміток");
  assert.match(src, /const connView = \(\) => \(\{ space: connSpace\(\), list: connState\.list, tools: connState\.tools, notes: connState\.notes,/);
});

test("connAction: дія над модулем, що вже в польоті, ігнорується; кожна дія веде у свою функцію", () => {
  const b = fnc("connAction");
  assert.match(b, /^\{\s*if \(act === 'retry'\) \{ loadConn\(\); return; \}\s*if \(act === 'cat'\) \{ connCatalog\(role\); return; \}/);
  assert.match(b, /let e = \(connState\.list \|\| \[\]\)\.find\(\(x\) => x\.id === id\);\s*if \(!e \|\| connState\.busy\.has\(id\)\) return;/);
  assert.match(b, /if \(act === 'check'\) \{ connCheck\(e\); return; \}/, "«Перевірити» панелі не заважає");
  assert.match(b, /if \(act === 'enable'\) openCnDrawer\(e, 'enable', via === 'catalog' \? \{ role \} : null\);\s*else if \(act === 'configure'\) openCnDrawer\(e, 'edit'\);\s*else if \(act === 'disable'\) askConnDisable\(e\);/,
    "«Вимкнути» з меню відкриває питання в картці, а не пише");
  /* Нові дії картки (етап Е): «⋯», клік по картці (за `cardModel(e).click`), відповіді питання, «Забрати довіру». */
  assert.match(b, /if \(act === 'menu'\) \{ toggleConnMenu\(id\); return; \}/);
  assert.match(b, /if \(act === 'card'\) \{ act = cardModel\(e\)\.click; if \(!act\) return; \}/);
  assert.match(b, /if \(act === 'askno'\) \{ cancelConnAsk\(\); return; \}/);
  assert.match(b, /if \(act === 'untrust'\) \{ connUntrust\(e\); return; \}/);
});

test("connAction: відкрита панель — інша панель і «Вимкнути» її модуля спершу закривають її (з питанням); чужий модуль — без закриття", () => {
  const b = fnc("connAction");
  assert.match(src, /async function connAction\(act, id, role, via = ''\) \{/);
  /* Умова: панель відкрита І (це не «Вимкнути», АБО «Вимкнути» саме її модуля). */
  assert.match(b, /if \(cnDrawer && \(act !== 'disable' \|\| cnDrawer\.id === id\)\) \{\s*const spaceId = connState\.spaceId;\s*if \(!\(await dismissCnDrawer\(\)\)\) return;/,
    "відмова людини (панель лишилась) чи запит у польоті — дія не йде далі");
  /* Після питання: той самий простір і свіжа картка, а не знімок до діалогу. */
  assert.match(b, /if \(!connOpen\(\) \|\| connState\.spaceId !== spaceId\) return;\s*e = \(connState\.list \|\| \[\]\)\.find\(\(x\) => x\.id === id\);\s*if \(!e \|\| connState\.busy\.has\(id\)\) return;/);
  assert.ok(b.indexOf("dismissCnDrawer()") < b.indexOf("openCnDrawer(e, 'enable'"), "закриття — ДО відкриття іншої панелі");
  assert.ok(b.indexOf("dismissCnDrawer()") < b.indexOf("askConnDisable(e)"), "закриття — ДО питання про вимкнення");
});

test("панель: фокус вертається після перемальовки на той самий контрол (запасний — перший доступний; під запитом — памʼять focusWant)", () => {
  const k = fnc("cnFocusKey");
  assert.match(k, /if \(!a \|\| !el\.contains\(a\)\) return null;/, "фокус поза панеллю (палітра мови, діалог) не чіпаємо");
  assert.match(k, /if \(a\.dataset\.cnField != null\) return `\[data-cn-field="\$\{CSS\.escape\(a\.dataset\.cnField\)\}"\]`;/);
  assert.match(k, /if \(a\.dataset\.cnDr\) \{\s*return `\[data-cn-dr="\$\{a\.dataset\.cnDr\}"\]\$\{a\.dataset\.key != null \? `\[data-key="\$\{CSS\.escape\(a\.dataset\.key\)\}"\]` : ''\}`;/, "«Стерти» — ще й за ключем секрету");
  const b = fnc("paintCnDrawer");
  const iRead = b.indexOf("cnFocusKey(el, document.activeElement)");
  const iPaint = b.indexOf("el.innerHTML = drawerHTML(");
  assert.ok(iRead > 0 && iRead < iPaint, "ключ береться ДО перемальовки (після неї старого вузла нема)");
  assert.match(b, /const want = cnDrawer\.focusWant \?\? live;/);
  assert.match(b, /if \(usable\(back\)\) \{ cnDrawer\.focusWant = null; back\.focus\(\{ preventScroll: true \}\); return; \}/);
  assert.match(b, /\.cn-dr-body \[data-cn-field\], \.cn-dr-foot button/, "запасний — перший доступний контрол тіла й футера");
  assert.match(b, /\.find\(usable\);\s*if \(first\) \{ cnDrawer\.focusWant = null; first\.focus\(\{ preventScroll: true \}\); return; \}/);
  assert.match(b, /cnDrawer\.focusWant = want;\s*el\.querySelector\('\[data-cn-dr="close"\]'\)\?\.focus\(\{ preventScroll: true \}\);/,
    "усе вимкнено (запит летить): фокус на хрестику, бажаний контрол запамʼятовано");
  assert.ok(b.indexOf("const usable") > iPaint, "перевірка «доступний» — після перемальовки (на новому вузлі)");
});

test("картка зайнята записом панелі ('save') від відповіді до кінця перечитування; відмова теж перечитує список", () => {
  const b = fnc("cnSubmit");
  assert.match(b, /cnCardBusy\(mine\.spaceId, mine\.id, true\);\s*try \{/);
  assert.match(b, /await afterModulesChange\(\);\s*\} finally \{\s*cnCardBusy\(mine\.spaceId, mine\.id, false\);\s*\}/, "знімається ПІСЛЯ перечитування, у finally");
  assert.ok(b.indexOf("cnCardBusy(mine.spaceId, mine.id, true)") < b.indexOf("closeCnDrawer()"), "картка зайнята ДО закриття панелі");
  const h = fnc("cnCardBusy");
  assert.match(h, /if \(!connOpen\(\) \|\| connState\.spaceId !== spaceId\) return;/, "лише той самий простір: чужий busy не чіпаємо");
  assert.match(h, /if \(on\) connState\.busy\.set\(id, 'save'\); else connState\.busy\.delete\(id\);\s*paintHome\(\);\s*if \(!on\) refocusCard\(id, 'configure'\);/);
  /* Відмова (HTTP, тайм-аут): сервер пише секрети раніше за решту — список перечитується ДО перевірки «панель та сама». */
  assert.match(b, /\} catch \(err\) \{\s*cnRefreshAfterRefusal\(mine\.spaceId\);\s*if \(cnDrawer !== mine\) return;/);
  assert.match(fnc("cnRefreshAfterRefusal"), /if \(connOpen\(\) && connState\.spaceId === spaceId\) loadConn\(\{ spaces: false \}\);/);
});

test("Esc, що закрив дропдаун смуги, не закриває ще й панель: дропдаун гасить подію, слухач панелі її поважає (і стоїть ПІЗНІШЕ)", () => {
  assert.match(src, /if \(ev\.key === 'Escape' && openDd && !ev\.isComposing\) \{\s*const wasSpaces = openDd === 'space';\s*openDd = null;\s*(?:\/\*[\s\S]*?\*\/\s*)?ev\.preventDefault\(\);\s*paintBar\(\);/);
  assert.ok(src.indexOf("ev.key === 'Escape' && openDd && !ev.isComposing") < src.indexOf("ev.key === 'Escape' && !ev.isComposing && !ev.defaultPrevented && cnDrawer"),
    "слухач дропдауна реєструється РАНІШЕ: інакше `defaultPrevented` ще не виставлено");
});

test("зайнятість картки: ставиться ДО запиту й знімається в finally/catch; «Вимкнути» знімає її лише коли свіжий список уже прийшов", () => {
  const c = fnc("connCheck");
  assert.match(c, /connState\.busy\.set\(e\.id, 'check'\); paintHome\(\);\s*try \{ await checkPost\(/);
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
  assert.match(b, /const c = ev\.target\.closest\('\[data-cn\]'\);\s*if \(c\) \{[\s\S]*?if \(ev\.target\.closest\('#th-menu'\)\) closeTaskMenu\(false\);\s*connAction\(c\.dataset\.cn, c\.dataset\.id, c\.dataset\.role\);\s*return;\s*\}/,
    "пункт меню «⋯» закриває меню ДО дії; `data-role` — для «Додати» ролі");
  assert.ok(iC < b.indexOf("const b = ev.target.closest('[data-th]');"), "делегація data-cn — раніше за data-th");
});

test("перший фокус після списку не краде фокус у палітри чи діалогу (Task 7: місце фокуса — focusConnLanding, роль — connFocusRole)", () => {
  assert.match(fnc("loadConn"),
    /if \(connFocusPending\) \{\s*connFocusPending = false;\s*const role = connFocusRole;\s*connFocusRole = '';\s*if \(!paletteOverlay && !askUp\(\)\) focusConnLanding\(role\);\s*\}/);
  /* Те, що раніше стояло в loadConn рядком, тепер — у focusConnLanding: без ролі й без картки ролі поведінка та сама (перша кнопка першої
     картки або «Спробувати ще», без прокрутки). */
  /* Етап Е: картка модуля ролі, інакше «Додати» її пунктирної картки; без ролі — перша картка (чи «Спробувати ще»/«Додати модуль»). */
  const f = fnc("focusConnLanding");
  assert.match(f, /home\?\.querySelector\(`\.mc\[data-id="\$\{CSS\.escape\(id\)\}"\]`\)/);
  assert.match(f, /home\?\.querySelector\(`\.mc--empty\[data-role="\$\{CSS\.escape\(role\)\}"\]`\)/);
  assert.match(f, /if \(card\) \{ \(card\.querySelector\('\.mc-open'\) \?\? card\.querySelector\('\[data-cn\]:not\(\[disabled\]\)'\)\)\?\.focus\(\); return; \}\s*if \(empty\) \{ empty\.querySelector\('\[data-cn="cat"\]'\)\?\.focus\(\); return; \}/);
  assert.match(f, /home\?\.querySelector\('\.mc-open, \[data-cn="retry"\], \[data-cn="cat"\]'\)/);
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

test("рамка: render({ keepFrame }) не переприсвоює frame.src (кожне присвоєння — перезавантаження); лише afterModulesChange його вмикає — і лише поки оверлей відкритий", () => {
  assert.match(src, /async function render\(\{ keepFrame = false \} = \{\}\) \{/);
  assert.match(fnc("render"), /applyMode\(task, \{ keepFrame \}\);/);
  assert.match(fnc("applyMode"), /if \(!keepFrame\) \{\s*frame\.src = /);
  assert.match(src, /function applyMode\(task, \{ keepFrame = false \} = \{\}\) \{/);
  /* Єдине місце, що тримає рамку: легкий шлях після запису модулів. Усі інші `render()` — з перезавантаженням. */
  assert.deepEqual([...src.matchAll(/render\(\{ keepFrame: [^}]+\}\)/g)].length, 1);
  assert.deepEqual([...src.matchAll(/render\(\{ keepFrame: true \}\)/g)].length, 0, "безумовного keepFrame: true нема");
  /* `homeOpen`, а не `true`: якщо людина вийшла з оверлея, поки запис летів, `leaveHome` уже відпрацював зі СТАРИМИ
     `capabilities`, і наступного не буде — рамку мусить оновити сам `afterModulesChange`. */
  assert.match(fnc("afterModulesChange"), /await render\(\{ keepFrame: homeOpen \}\);/);
});

test("3c: «Довіритись…» і «Чому не можна…» картки ведуть у connTrust; простір фіксується ДО діалогу", () => {
  assert.match(fnc("connAction"), /else if \(act === 'trust' \|\| act === 'trustinfo'\) connTrust\(e, act\);/);
  const b = fnc("connTrust");
  assert.match(b, /refocusCard\(e\.id, act\)/, "фокус вертається на ту саму дію (trust чи trustinfo)");
  assert.ok(b.indexOf("const spaceId = connState.spaceId;") < b.indexOf("openTrust(e, spaceId)"));
});

test("3c: openTrust — свіжі дані, діалог, довіра через trustPost (своя стеля); module-changed — знову з позначкою; «Забрати довіру» — після закриття", () => {
  const b = fnc("openTrust");
  assert.match(b, /formApi\(`\/api\/module-trust\?space=\$\{encodeURIComponent\(spaceId\)\}&id=\$\{encodeURIComponent\(entry\.id\)\}`\)/);
  assert.match(b, /askForm\(\(\) => trustDialogHTML\(\{ \.\.\.d, reopened \}\)/);
  assert.match(b, /trustPost\(\{ space: spaceId, id: d\.id, hash: d\.hash, lang: getLang\(\) \}\)/);
  assert.match(b, /if \(err\?\.code === 'module-changed'\) \{ again = true; return undefined; \}/);
  assert.match(b, /if \(again\) \{ reopened = true; continue; \}/);
  assert.match(b, /if \(form\.getAttribute\('aria-busy'\) === 'true'\) return;/, "під час запиту «Забрати довіру» нічого не позначає");
  assert.ok(b.indexOf("await askForm(") < b.indexOf("untrustFlow(entry, spaceId)"), "питання — лише після закриття діалогу");
  assert.match(b, /await afterModulesChange\(\);/);
  const p = fnc("trustPost");
  assert.match(p, /setTimeout\(\(\) => ctl\.abort\(\), TRUST_POST_TIMEOUT_MS\)/);
  assert.match(p, /\.finally\(\(\) => clearTimeout\(timer\)\)/);
  assert.match(src, /import \{ TRUST_POST_TIMEOUT_MS, trustDialogHTML \} from '\.\/trust-view\.js';/);
});

test("3c: «Забрати довіру» — небезпечне питання, запит у зафіксований простір, далі afterModulesChange; у панелі — модуль і простір ДО її закриття", () => {
  const u = fnc("untrustFlow");
  assert.match(u, /askYesNo\(lines\.join\('\\n\\n'\), \{ yes: t\('cnUntrust'\), danger: true \}\)/);
  assert.match(u, /postForm\('\/api\/module-untrust', \{ space: spaceId, id: entry\.id \}\)/);
  assert.ok(u.indexOf("askYesNo(") < u.indexOf("postForm("));
  assert.match(u, /await afterModulesChange\(\);/);
  const d = fnc("cnDrawerUntrust");
  assert.ok(d.indexOf("const { entry, spaceId } = cnDrawer;") < d.indexOf("dismissCnDrawer()"));
  assert.match(fnc("wireCnDrawer"), /else if \(a === 'untrust'\) cnDrawerUntrust\(\);/);
});

test("3c (ревʼю Task 6): запасний фокус панелі не падає на руйнівну «Забрати довіру» — вона перша у футері", () => {
  assert.match(fnc("paintCnDrawer"), /\.cn-dr-foot button:not\(\[data-cn-dr="untrust"\]\)/);
});

test("3c (ревʼю Task 6): коментарі про види зайнятості картки (`busy`) не обіцяють того, чого код не ставить", () => {
  const viewSrc = readFileSync(new URL("../app/connections-view.js", import.meta.url), "utf8");
  const kinds = (text, re) => (re.exec(text)?.[1] ?? "").split("|").map((x) => x.replace(/'/g, "")).filter(Boolean);
  const declared = kinds(src, /id → ((?:'\w+'\|?)+)\)\. `seq`/);
  assert.deepEqual(declared.sort(), ["check", "disable", "save"], "коментар біля connState");
  assert.deepEqual(kinds(viewSrc, /busy {3}— Map id → ((?:'\w+'\|?)+):/).sort(), declared.sort(), "коментар у connections-view.js — той самий перелік");
  for (const k of declared) assert.match(src, new RegExp(`connState\\.busy\\.set\\([^)]*'${k}'\\)`), `код ніде не ставить busy '${k}'`);
});

test("етап Е: розділ «Налаштувань» — памʼятається; ⌘K, фішка, кнопка «Задач» і вхід із роллю ведуть у «Модулі», шестерня — ні", () => {
  assert.match(src, /let connSec = \(\(\) => \{ try \{ return readSec\(localStorage\.getItem\(SEC_KEY\)\); \}/);
  assert.match(fnc("setConnSec"), /connAsk = null;\s*connSec = readSec\(sec\);\s*try \{ localStorage\.setItem\(SEC_KEY, connSec\); \} catch/);
  assert.match(fnc("enterHome"), /if \(connFocusRole\) setConnSec\('mods'\);\s*paintHome\(\);\s*loadConn/, "вхід із роллю → «Модулі»");
  assert.match(fnc("wireHome"), /case 'csec': if \(readSec\(v\) !== connSec\) \{ setConnSec\(v\); paintHome\(\); if \(connSec === 'agents'\) loadAgents\(\); if \(connSec === 'upd'\) pollUpdate\(\); \} break;/);
  const settings = /\n  settings: async \(\) => \{[\s\S]*?\n  \},/.exec(src)[0];
  assert.doesNotMatch(settings, /setConnSec/, "шестерня веде в ОСТАННІЙ розділ, не скидає його");
  assert.match(src, /sec: connSec, ask: connAsk, agents: agentsSt\.data, agentsBusy: agentsSt\.busy,/, "connView несе розділ, питання «Вимкнути?» і стан AGENTS.md у розмітку");
  assert.match(src, /general: \{ lang: getLang\(\), canInstall: pwa\.canInstall\(\), standalone: pwa\.isStandalone\(\) \}, update: updateInfo, updChecking: updateChecking \}\);/,
    "connView несе мову, стан встановлення й оновлення для групи «Застосунок»");
});

/* ── «Налаштування → Модулі» (етап Е, Task 2): меню «⋯», клавіатура картки, питання «Вимкнути?» ── */

test("етап Е: меню «⋯» модуля — той самий `#th-menu`; «⋯» картки (`.mc-more`) — теж «якір»: фокус назад, клік повз закриває", () => {
  assert.match(src, /const moreSel = \(id\) => `\.th-more\[data-id="\$\{CSS\.escape\(id\)\}"\], \.mc-more\[data-id="\$\{CSS\.escape\(id\)\}"\]`;/);
  assert.match(fnc("closeTaskMenu"), /homeNode\(\)\?\.querySelector\(moreSel\(id\)\)/, "закриття повертає фокус на «⋯» і задачі, і модуля");
  assert.match(src, /const refocusMore = \(id\) => \{ if \(id\) homeNode\(\)\?\.querySelector\(moreSel\(id\)\)\?\.focus/);
  assert.equal([...src.matchAll(/!ev\.target\.closest\('\.th-more, \.mc-more'\)/g)].length, 2, "обидва закривачі меню (pointerdown і click) знають про `.mc-more`");
  const b = fnc("toggleConnMenu");
  assert.match(b, /if \(m && m\.dataset\.for === id\) \{ closeTaskMenu\(\); return; \}/, "повторний клік по «⋯» закриває");
  assert.match(b, /connMenuHTML\(e\)/);
  assert.match(b, /btn\.setAttribute\('aria-expanded', 'true'\);\s*menu\.dataset\.for = id;\s*menu\.querySelector\('\[role="menuitem"\]'\)\?\.focus/, "фокус — на перший пункт");
});

test("етап Е: клавіші меню — один спільний `menuKeys` для задач і модулів; розділ «Модулі» має свій keydown (лише Esc знімає питання; Enter/Пробіл — рідна кнопка `.mc-open`)", () => {
  const m = fnc("menuKeys");
  assert.match(m, /if \(ev\.key === 'Escape'\) \{ ev\.preventDefault\(\); closeTaskMenu\(\); \}/, "Esc — закрити з фокусом на «⋯»");
  assert.match(m, /else if \(ev\.key === 'Tab'\) closeTaskMenu\(\);/);
  assert.match(m, /\(at \+ \(ev\.key === 'ArrowDown' \? 1 : -1\) \+ items\.length\) % items\.length/, "стрілки по колу");
  assert.ok(src.includes("  if (menuKeys(ev, a)) return;\n  /* Поле назви на картці"), "екран «Задачі» бере меню з того самого `menuKeys`");
  const i = src.indexOf("/** Клавіатура розділу «Модулі»");
  assert.ok(i > 0);
  const k = noComments(src.slice(i, src.indexOf("/** Клавіатура екрана. `/`")));
  assert.match(k, /if \(!homeOpen \|\| homePage !== 'conn' \|\| ev\.isComposing \|\| paletteOverlay \|\| askUp\(\)\) return;/, "лише на «Налаштуваннях», не з-під палітри/діалогу/IME");
  assert.match(k, /if \(menuKeys\(ev, a\)\) return;/);
  assert.match(k, /if \(ev\.key === 'Escape' && connAsk\) \{ ev\.preventDefault\(\); cancelConnAsk\(\); return; \}/);
  /* a11y (рев'ю Task 2): картка не `role=button`, тож власного Enter/Пробіл на ній нема — їх дає нативна кнопка-назва `.mc-open`. */
  assert.doesNotMatch(k, /ev\.key === 'Enter'|ev\.key === ' '|connAction\('card'/, "обробника Enter/Пробіл на картці більше нема");
  assert.doesNotMatch(k, /classList\?\.contains\('mc'\)/);
});

test("етап Е: питання «Вимкнути?» знімається кліком повз картку (pointerdown і click) — лише на «Налаштуваннях», без звернення до connAsk на «Задачах»", () => {
  assert.match(fnc("homePointerDown"), /if \(homePage === 'conn' && connAsk && !ev\.target\.closest\('\.mc--ask'\)\) \{ homeEatUntil = performance\.now\(\) \+ 500; cancelConnAsk\(false\); \}/);
  assert.match(fnc("wireHome"), /if \(homePage === 'conn' && connAsk && !ev\.target\.closest\('\.mc--ask'\)\) \{ cancelConnAsk\(false\); return; \}/);
});

test("етап Е: «Забрати довіру» з меню картки йде в untrustFlow", () => {
  assert.match(fnc("connUntrust"), /await untrustFlow\(e, spaceId\);\s*if \(connOpen\(\) && connState\.spaceId === spaceId\) refocusCard\(e\.id, 'card'\);/);
});

test("каталог: «Додати» (`cat`) відкриває `connCatalog(role)`; діалог — `askForm` над `catalogGroups`; вибір — requestSubmit, далі шухляда «Підключити» з каталогу", () => {
  assert.doesNotMatch(src, /\nfunction connCatalog\(role\) \{\}\n/, "заглушки нема");
  const b = fnc("connCatalog");
  assert.match(b, /if \(!connOpen\(\) \|\| connState\.list == null\) return;\s*const spaceId = connState\.spaceId;/, "список ще вантажиться — каталогу нема");
  assert.match(b, /const groups = catalogGroups\(connState\.list, modName\);/);
  assert.match(b, /await askForm\(\(\) => catFormHTML\(catListHTML\(groups, role\), 'list'\), \{/);
  assert.match(b, /if \(b\.dataset\.catPick !== undefined\) \{ picked = b\.dataset\.catPick; form\.requestSubmit\(\); return; \}/);
  assert.match(b, /if \(b\.hasAttribute\('data-cat-own'\)\) \{ page\('own'\); form\.querySelector\('#own-what'\)\?\.focus\(\); return; \}/);
  assert.match(b, /if \(b\.hasAttribute\('data-cat-back'\)\) \{ page\('list'\); form\.querySelector\('\[data-cat-own\]'\)\?\.focus\(\); return; \}/);
  assert.match(b, /if \(b\.dataset\.a === 'cancel'\) \{ x\?\.click\(\); return; \}/, "«Закрити» другої сторінки — через хрестик шапки, до якого `askForm` чіпляє закриття");
  /* Копіювання: буфер — у самому обробнику кліку; відмова → виділити запит, тост лише коли справді скопійовано. */
  assert.match(b, /await navigator\.clipboard\.writeText\(pre\.textContent\);\s*toast\(t\('ownCopied'\)\);\s*\} catch \(err\) \{\s*getSelection\(\)\?\.selectAllChildren\(pre\);/);
  assert.match(b, /ownPrompt\(\{ space: sp\?\.name \?\? '', folder: sp\?\.path \?\? '', authoring: connState\.authoring, what, lang: getLang\(\) \}\)/);
  assert.match(b, /ev\.target\.id !== 'own-what'[\s\S]*?#own-prompt'\)\.textContent = promptNow\(\)/, "запит оновлюється на кожен символ");
  /* Фокус назад: пунктирна картка ролі або «Додати модуль» у голові. */
  assert.match(b, /focusBack: \(\) => \(role \? homeNode\(\)\?\.querySelector\(`\[data-cn="cat"\]\[data-role="\$\{CSS\.escape\(role\)\}"\]`\) : null\)\s*\?\? homeNode\(\)\?\.querySelector\('\.th-head \[data-cn="cat"\]'\),/);
  /* Після діалогу: той самий простір → шухляда з каталогу; без налаштувань — одразу запис. */
  assert.match(b, /if \(picked === null \|\| !connOpen\(\) \|\| connState\.spaceId !== spaceId\) return;/);
  assert.match(b, /await connAction\('enable', picked, role, 'catalog'\);\s*if \(cnDrawer\?\.id === picked && cnDrawer\.mode === 'enable' && cnDrawer\.fields\.length === 0\) cnSubmit\(\);/);
});

test("каталог: шухляда з каталогу не питає «Замінити?» першого разу (кнопка вже назвала тримачів) і вертає фокус на «Додати"+"»", () => {
  const o = fnc("openCnDrawer");
  assert.match(o, /opener: fromCatalog \? \{ act: 'cat', id: e\.id, role: fromCatalog\.role \|\| '' \}/);
  assert.match(o, /\.\.\.\(fromCatalog \? \{ catalogHolders: roleHolders\(e, connState\.list\) \} : \{\}\)/, "знімок тримачів — на момент відкриття шухляди");
  assert.match(fnc("closeCnDrawer"), /if \(op\.act === 'cat'\) \{[\s\S]*?\.th-head \[data-cn="cat"\][\s\S]*?return;\s*\}/);
});

/* ── «В Figma» як інструмент простору (етап Е): проводка в app.js ── */
test("інструмент простору: `tool:…` не доходить до пошуку модуля; дії toolon/toolask/askyes; запис — space-tool зі станом із відповіді", () => {
  const a = fnc("connAction");
  assert.match(a, /if \(id\?\.startsWith\('tool:'\)\) \{ connToolAction\(act, id\); return; \}\s*let e = \(connState\.list/, "інструмент — ДО `find` у списку модулів");
  const t = fnc("connToolAction");
  assert.match(t, /act === 'toolask'[\s\S]*?connAsk = \{ id \};/);
  assert.match(t, /act === 'askyes'\) \{ if \(connAsk\?\.id === id\) connToolSet\(card\.tool, false\);/, "«Так» лише на питанні САМОЇ картки");
  assert.match(t, /act === 'toolon'\) connToolSet\(card\.tool, true\);/);
  assert.match(t, /act === 'askno'\) \{ cancelConnAsk\(\); return; \}/);
  const s = fnc("connToolSet");
  assert.match(s, /postForm\('\/api\/space-tool', \{ space: spaceId, tool, on \}\)/);
  assert.match(s, /connState\.tools = saved\.tools;\s*applySpaceTools\(spaceId, saved\.tools\);/, "смуга й ⌘K — з відповіді, без render()");
  assert.doesNotMatch(s, /render\(/, "макет не перезавантажується");
  const p = fnc("applySpaceTools");
  assert.match(p, /spacesResp = \{ \.\.\.spacesResp, spaces: spacesResp\.spaces\.map\(patch\) \}/);
  assert.match(p, /curTask = \{ \.\.\.curTask, space: patch\(curTask\.space\) \}/);
  assert.match(p, /paintBar\(\);/);
  assert.match(fnc("toggleConnMenu"), /toolMenuHTML\(card\)/);
});

/* ── «Налаштування → AGENTS.md» (етап Е, Task 6) ── */
test("AGENTS.md: читається при вході на сторінку (loadConn) і при переході в розділ; свіжий вхід скидає стан", () => {
  assert.match(fnc("loadConn"), /connAsk = null;\s*paintHome\(\);\s*\}\s*loadAgents\(\);/, "після перемикання простору — читання AGENTS.md");
  assert.match(fnc("enterHome"), /agentsSt\.spaceId = null; agentsSt\.data = null; agentsSt\.busy = false;/, "свіжий вхід не показує дані попереднього візиту");
  assert.match(fnc("wireHome"), /case 'ag': agentsAction\(v\); break;/);
  const b = fnc("loadAgents");
  assert.match(b, /api\(`\/api\/agents-md\?space=\$\{encodeURIComponent\(sid\)\}`\)/, "явний простір сторінки");
  assert.match(b, /seq !== agentsSt\.seq \|\| !connOpen\(\) \|\| connState\.spaceId !== sid\) return;/, "запізніла відповідь відкидається");
  assert.match(b, /data = \{ failed: \{ code: e\?\.code \?\? null \} \}/, "збій не кидає — малює розділ");
});

test("AGENTS.md: запис — POST з явним простором, тост за створення/оновлення, фокус на «Скопіювати»; копіювання — writeText синхронно з кліку", () => {
  const w = fnc("agentsWrite");
  assert.match(w, /post\('\/api\/agents-md', \{ space: sid \}\)/);
  assert.match(w, /toast\(t\(created \? 'agCreated' : 'agUpdated'\)\)/);
  assert.match(w, /agentsSt\.seq \+= 1;/, "читання, що летіло до запису, застаріло");
  assert.match(w, /if \(connSec === 'agents'\) focusAgents\(\);/);
  const c = fnc("agentsCopy");
  assert.match(c, /navigator\.clipboard\.writeText\(text\)\.then\(\(\) => toast\(t\(doneKey\)\), sel\)/);
  assert.match(c, /selectAllChildren/, "відмова буфера — виділяємо текст");
  assert.doesNotMatch(fnc("agentsAction"), /await/, "writeText — у тому ж такті, що й клік");
});

/* ── «Налаштування → Застосунок» (етап Е, Task 8): проводка мови, встановлення й оновлення ── */

test("етап Е, «Застосунок»: мова — той самий switchLang, що ⌘K; встановлення — pwa.install; оновлення — наявні checkUpdateNow/openUpdateDialog", () => {
  const w = fnc("wireHome");
  assert.match(w, /case 'lang': switchLang\(v\);/);
  assert.match(w, /case 'pwa': pwa\.install\(\)\.then\(\(\) => repaintSettingsSec\('app'\)\);/);
  assert.match(w, /case 'up': if \(v === 'check'\) checkUpdateNow\(\); else openUpdateDialog\(\);/);
  assert.match(src, /act === 'lang'\) \{ switchLang\(a\.val\); return; \}/, "⌘K і розділ ділять один шлях мови");
  assert.match(src, /window\.addEventListener\('beforeinstallprompt', \(\) => repaintSettingsSec\('app'\)\);/);
  const c = fnc("checkUpdateNow");
  assert.match(c, /updateChecking = true;\s*repaintSettingsSec\('upd'\);/, "кнопка зайнята ще до запиту");
  assert.match(c, /finally \{\s*updateChecking = false;[\s\S]*data-th="up"\]\[data-v="check"\]'\)\?\.focus/, "фокус вертається на кнопку");
});

test("AGENTS.md, рядок «Claude Code»: «Підключити»/«Оновити» — POST {claude:true}, «Відключити» — POST {hook:false}; тост залежить від відповіді", () => {
  const c = fnc("agentsClaude");
  assert.match(c, /claude: true/);
  assert.match(c, /d\.hookError \? 'frHookFailed'/, "збій хука при підключеному CLAUDE.md — тост збою");
  assert.match(c, /d\.hook\?\.state === 'ok' \? 'frHookConnected' : 'frClaudeConnected'/);
  const u = fnc("agentsUnhook");
  assert.match(u, /hook: false/);
  assert.match(u, /'frHookDisconnected'/);
  assert.match(fnc("agentsAction"), /v === 'unhook'\) agentsUnhook\(\)/);
  assert.match(fnc("agentsRowCall"), /agentsSt\.seq \+= 1;/, "читання, що летіло до запису, застаріло");
  assert.doesNotMatch(fnc("agentsAction"), /await/, "writeText — у тому ж такті, що й клік");
});

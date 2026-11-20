/**
 * Діалог довіри своєму модулю (Deai 0.7.0, етап 3c; спека, «Діалог довіри»): розмітка `trustDialogHTML` для `askForm`
 * (контракт форми, фокус на «Скасувати», екранування всього з диска, обрізання до 80, позначки змін, режим `refused`),
 * `sizeText`, стеля запиту довіри, правила CSS і словник.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { DICT } from "../app/i18n.js";
import { TR_MAX, TR_REMOVED_MAX, TRUST_POST_TIMEOUT_MS, cutMid, sizeText, trustDialogHTML } from "../app/trust-view.js";

const read = (f) => readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
const base = (over = {}) => ({
  id: "acme", name: "Acme", version: "1.2", roles: ["publish"], path: "~/work/alpha/modules/acme",
  state: "untrusted", record: false, hash: "ab".repeat(32),
  settings: [{ key: "token", type: "secret", label: "Token", public: false }, { key: "site", type: "text", label: "Site id" }],
  files: [{ path: "module.json", size: 120, change: "new" }, { path: "server.py", size: 12034, change: "new" }],
  removed: [], total: { files: 2, bytes: 12154 }, ...over,
});

test("контракт askForm: один form-діалог, «Довірити» — submit data-a=ok, «Скасувати» — data-a=cancel з ЄДИНИМ data-autofocus", () => {
  const h = trustDialogHTML(base());
  assert.equal((h.match(/<form/g) || []).length, 1);
  assert.match(h, /<form class="cv-form tr" novalidate role="dialog" aria-modal="true" aria-labelledby="tr-h">/);
  assert.match(h, /<h2 class="cv-form-h" id="tr-h">Довіритись модулю «Acme»\?<\/h2>/);
  assert.match(h, /<button type="submit" data-a="ok">Довірити<\/button>/);
  assert.match(h, /<button type="button" data-a="cancel" data-autofocus>Скасувати<\/button>/);
  assert.equal((h.match(/data-autofocus/g) || []).length, 1, "Enter, натиснутий не дивлячись, не довіряє");
  assert.match(h, /<p class="cv-form-err" id="cv-form-err" role="alert" data-form-error hidden><\/p>/);
  assert.match(h, /<p class="tr-wait" data-tr-wait role="status" hidden>Підтвердіть у системному вікні…<\/p>/);
  assert.doesNotMatch(h, /data-tr="untrust"/, "без запису довіри забирати нічого");
});

test("зміст: версія й ролі, шлях, відбиток 12 знаків, попередження, «Просить» з позначками секретів, файли з розмірами", () => {
  const h = trustDialogHTML(base({ settings: [
    { key: "token", type: "secret", label: "Token", public: false },
    { key: "anon", type: "secret", label: "Anon key", public: true },
    { key: "site", type: "text", label: "Site id" },
  ] }));
  assert.match(h, /<p class="tr-meta">v1\.2 · Публікація<\/p>/);
  assert.match(h, /<code>~\/work\/alpha\/modules\/acme<\/code> · Відбиток abababababab</);
  assert.match(h, /class="tr-warn".*з вашими правами.*Після «Довірити» система попросить/s);
  assert.doesNotMatch(h, /сторінках канваса/, "попередження про JavaScript — лише для ролі comments");
  assert.match(h, /<li>Token <span class="tr-mark">секрет<\/span><\/li>/);
  assert.match(h, /<li>Anon key <span class="tr-mark">публічний \(потрапляє в сторінки\)<\/span><\/li>/);
  assert.match(h, /<li>Site id<\/li>/);
  assert.match(h, /Файли \(2, 11,9 КБ\)/);
  assert.match(h, /<ul class="tr-files" tabindex="0" aria-label="Файли модуля">/);
  assert.match(h, /<code>server\.py<\/code><span class="tr-size">11,8 КБ<\/span><\/li>/);
  assert.doesNotMatch(h, /tr-mark">новий/, "без запису довіри «новий» — кожен файл, позначка нічого не каже");
  assert.match(trustDialogHTML(base({ settings: [] })), /<p class="tr-none">Налаштувань не просить\.<\/p>/);
  assert.match(trustDialogHTML(base({ roles: ["comments"] })), /Його JavaScript виконуватиметься в сторінках канваса/);
});

test("нова версія: свій заголовок, лічильник змін, позначки «новий»/«змінено», рядок «Прибрано»; запис — кнопка «Забрати довіру»", () => {
  const h = trustDialogHTML(base({ state: "changed", record: true,
    files: [{ path: "module.json", size: 1, change: "same" }, { path: "server.py", size: 2, change: "changed" },
      { path: "new.js", size: 3, change: "new" }],
    removed: [{ path: "old.js", size: 9 }], total: { files: 3, bytes: 6 } }));
  assert.match(h, /id="tr-h">Довіритись новій версії «Acme»\?</);
  assert.match(h, /Файли \(3, 6 Б\) · змінено від минулої довіри: 3/);
  assert.match(h, /<code>server\.py<\/code><span class="tr-size">2 Б<\/span><span class="tr-mark">змінено<\/span>/);
  assert.match(h, /<code>new\.js<\/code><span class="tr-size">3 Б<\/span><span class="tr-mark">новий<\/span>/);
  assert.match(h, /<code>module\.json<\/code><span class="tr-size">1 Б<\/span><\/li>/, "незмінний — без позначки");
  assert.match(h, /<p class="tr-removed">Прибрано: old\.js<\/p>/);
  assert.match(h, /<button type="button" class="tr-untrust" data-tr="untrust">Забрати довіру<\/button>/);
});

test("refused: без «Довірити» й попередження, причина і деталь, «Закрити» з фокусом; «Забрати довіру» — якщо запис є", () => {
  const h = trustDialogHTML({ id: "acme", name: "Acme", version: "1", roles: ["publish"], path: "~/m/acme", state: "refused",
    record: true, refused: { code: "symlink", detail: "alias.py: symbolic link" } });
  assert.doesNotMatch(h, /data-a="ok"|tr-warn|Відбиток|tr-files/);
  assert.match(h, /<p class="tr-refused" role="alert">.*У теці є символьне посилання\.<span class="cn-why-detail">alias\.py: symbolic link<\/span>/s);
  assert.doesNotMatch(h, /Цій теці не можна довіритись/, "тіло не повторює заголовок");
  assert.match(h, /id="tr-h">Модулю «Acme» не можна довіритись</, "заголовок відмови, а не питання «Довіритись модулю…?»");
  assert.doesNotMatch(h, /Довіритись модулю/);
  assert.equal(DICT.en.trTitleRefused("Acme"), "“Acme” cannot be trusted", "англійський заголовок відмови");
  assert.equal(DICT.en.trRefused("because"), "because", "англійське тіло — лише причина, без повтору заголовка");
  assert.match(h, /<button type="button" data-a="cancel" data-autofocus>Закрити<\/button>/);
  assert.match(h, /data-tr="untrust"/);
  assert.match(trustDialogHTML({ id: "x", state: "refused", refused: { code: "zzz" } }), /Тека не годиться для модуля\./);
});

test("усе з диска — текст: <img onerror> у назві, шляху, файлі, мітці й деталі не стає тегом; рядки обрізано до TR_MAX", () => {
  const evil = '<img src=x onerror="alert(1)">';
  const h = trustDialogHTML(base({ name: evil, version: evil, path: evil, hash: evil, roles: [evil], settings: [{ key: "k", type: "text", label: evil }],
    files: [{ path: evil, size: 1, change: "new" }], removed: [{ path: evil, size: 1 }], record: true }));
  assert.doesNotMatch(h, /<img/);
  assert.match(h, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  const r = trustDialogHTML({ id: "x", state: "refused", refused: { code: "symlink", detail: evil } });
  assert.doesNotMatch(r, /<img/);
  const long = "n".repeat(200);
  const l = trustDialogHTML(base({ name: long, files: [{ path: `${long}.py`, size: 1, change: "new" }] }));
  assert.ok(l.includes(`«${"n".repeat(TR_MAX - 1)}…»`), "назва обрізана");
  assert.ok(l.includes(`<code>${"n".repeat(TR_MAX - 1)}…</code>`), "імʼя файла обрізане");
  assert.equal(TR_MAX, 80);
});

test("кожне поле з диска обрізається до TR_MAX: версія, роль, мітка, файл, прибраний файл, шлях, назва й деталь відмови", () => {
  const long = "n".repeat(200);
  const cutText = `${"n".repeat(TR_MAX - 1)}…`;
  const h = trustDialogHTML(base({ version: long, roles: [long], path: long, settings: [{ key: "k", type: "text", label: long }],
    files: [{ path: long, size: 1, change: "new" }], removed: [{ path: long, size: 1 }], record: true }));
  assert.doesNotMatch(h, /n{81,}/, "якесь поле пройшло без обрізання");
  assert.ok(h.includes(cutText), "контроль: обрізаний рядок є");
  for (const [field, over] of Object.entries({
    версія: { version: long }, роль: { roles: [long] }, шлях: { path: long }, мітка: { settings: [{ key: "k", type: "text", label: long }] },
    файл: { files: [{ path: long, size: 1, change: "new" }] }, прибраний: { removed: [{ path: long, size: 1 }] },
  })) assert.doesNotMatch(trustDialogHTML(base(over)), /n{81,}/, `${field} не обрізано`);
  const r = trustDialogHTML({ id: "x", name: long, state: "refused", refused: { code: "symlink", detail: long } });
  assert.doesNotMatch(r, /n{81,}/);
  assert.ok(r.includes(`<span class="cn-why-detail">${cutText}</span>`), "деталь відмови обрізана");
});

test("«Прибрано» має стелю: перші TR_REMOVED_MAX імен і «і ще N»; рівно стеля — без «і ще»", () => {
  assert.equal(TR_REMOVED_MAX, 10);
  const gone = (n) => Array.from({ length: n }, (_, i) => ({ path: `old${i + 1}.js`, size: 1 }));
  const row = (n) => /<p class="tr-removed">([^<]*)<\/p>/.exec(trustDialogHTML(base({ state: "changed", record: true, removed: gone(n) })))?.[1];
  assert.equal(row(12), `Прибрано: ${Array.from({ length: 10 }, (_, i) => `old${i + 1}.js`).join(", ")}, і ще 2`);
  assert.doesNotMatch(row(12), /old11\.js/, "11-го імені нема");
  assert.equal(row(10), `Прибрано: ${Array.from({ length: 10 }, (_, i) => `old${i + 1}.js`).join(", ")}`, "рівно 10 — без «і ще»");
  assert.doesNotMatch(row(10), /і ще/);
  assert.equal(row(11), `Прибрано: ${Array.from({ length: 10 }, (_, i) => `old${i + 1}.js`).join(", ")}, і ще 1`);
  assert.equal(row(1), "Прибрано: old1.js");
  /* лічильник у шапці файлів лишається повним (усі прибрані), стеля — лише в переліку імен */
  assert.match(trustDialogHTML(base({ state: "changed", record: true, files: [], removed: gone(12) })), /змінено від минулої довіри: 12</);
  assert.equal(DICT.en.trRemovedMore(2), "and 2 more");
  assert.equal(DICT.uk.trRemovedMore(2), "і ще 2");
});

test("cutMid: як `_clean(…, middle=True)` системного вікна — голова (n-1)//3, «…», хвіст; шлях у діалозі однаковий із вікном", () => {
  const hundred = `${"a".repeat(100 - "/modules/memo-own".length)}/modules/memo-own`;
  assert.equal(hundred.length, 100);
  const c = cutMid(hundred);
  assert.equal(c.length, TR_MAX, "рівно TR_MAX");
  assert.ok(c.startsWith(hundred.slice(0, 26)), "голова — перші 26");
  assert.equal(c[26], "…");
  assert.ok(c.endsWith("/modules/memo-own"), "хвіст із текою модуля збережено");
  assert.equal(c, `${hundred.slice(0, 26)}…${hundred.slice(100 - 53)}`);
  const exact = "x".repeat(TR_MAX);
  assert.equal(cutMid(exact), exact, "рівно TR_MAX — без змін");
  assert.equal(cutMid("~/short/modules/acme"), "~/short/modules/acme", "короткий — без змін");
  assert.equal(cutMid(undefined), "");
  assert.equal(cutMid("y".repeat(TR_MAX + 1)).length, TR_MAX);
  /* лише шлях йде з середини; решта полів — як було, із кінця */
  const h = trustDialogHTML(base({ path: hundred, name: "n".repeat(100) }));
  assert.ok(h.includes(`<code>${c}</code>`), "шлях у діалозі — cutMid");
  assert.ok(h.includes(`«${"n".repeat(TR_MAX - 1)}…»`), "назва — зрізана з кінця");
});

test("cut і cutMid (ревʼю Task 7): спершу прибирають Cc/Cf/Cs/Zl/Zp, далі міряють у code points — як `module_trust._clean` (емодзі, без самотнього сурогата)", () => {
  const lone = /[\ud800-\udfff]/u;   // у режимі `u` збігається лише з самотнім сурогатом
  /* шлях із 72 code points (довжина UTF-16 = 144 > 80) вміщається — не ріжеться */
  const e72 = "😀".repeat(72);
  assert.ok(e72.length > TR_MAX && Array.from(e72).length <= TR_MAX);
  assert.equal(cutMid(e72), e72, "cutMid: 72 code points не ріжеться");
  assert.equal(cutMid("😀".repeat(TR_MAX)), "😀".repeat(TR_MAX), "рівно TR_MAX code points — без змін");
  const inDlg = trustDialogHTML(base({ path: e72, name: e72, version: e72 }));
  assert.ok(inDlg.includes(`<code>${e72}</code>`), "шлях у діалозі цілий");
  assert.ok(inDlg.includes(`«${e72}»`), "назва в заголовку ціла (cut)");
  /* 100 емодзі — ріжеться до рівно 80 code points, без � і без самотнього сурогата */
  const e100 = "😀".repeat(100);
  for (const [what, out] of [["cutMid", cutMid(e100)], ["cut (назва)", /модулю «([^»]*)»\?/.exec(trustDialogHTML(base({ name: e100 })))?.[1] ?? ""]]) {
    assert.equal(Array.from(out).length, TR_MAX, `${what}: рівно ${TR_MAX} code points`);
    assert.doesNotMatch(out, /\ufffd/u, `${what}: без �`);
    assert.doesNotMatch(out, lone, `${what}: без самотнього сурогата`);
    assert.ok(out.includes("…"), `${what}: є «…»`);
  }
  const mid = cutMid(e100);
  assert.equal(mid, `${"😀".repeat(26)}…${"😀".repeat(53)}`, "голова (n-1)//3 = 26, хвіст 53 — у code points");
  /* самотній сурогат із module.json не доходить до розмітки */
  assert.doesNotMatch(cutMid(`a\ud800b${"x".repeat(100)}`), lone);
  assert.equal(cutMid("a\ud800b"), "ab");
  /* bidi-перевизначення й керування прибрано (і з назви — cut, і зі шляху — cutMid), далі міряється вже очищене */
  assert.equal(cutMid("a\u202eb"), "ab");
  assert.equal(cutMid("a\u0007b\u2028c\u2029d\u200be"), "abcde", "Cc, Zl, Zp, Cf");
  assert.ok(trustDialogHTML(base({ name: "a\u202eb" })).includes("«ab»"), "cut: «a\\u202eb» → «ab»");
  assert.ok(trustDialogHTML(base({ version: "1\u202e2" })).includes("v12"), "cut: версія");
  const padded = `${"n".repeat(TR_MAX)}\u202e`;   // рівно TR_MAX значущих + керівний знак — після очищення не ріжеться
  assert.ok(trustDialogHTML(base({ name: padded })).includes(`«${"n".repeat(TR_MAX)}»`), "очищення — ДО виміру");
  assert.equal(cutMid(padded), "n".repeat(TR_MAX));
});

test("повторне відкриття: рядок угорі «Тека змінилась…»", () => {
  assert.match(trustDialogHTML(base({ reopened: true })), /<p class="tr-reopened" role="status">Тека змінилась, поки діалог був відкритий/);
  assert.doesNotMatch(trustDialogHTML(base()), /tr-reopened/);
});

test("sizeText: байти до 1 КБ, далі КБ / МБ з однією цифрою після коми", () => {
  assert.equal(sizeText(0), "0 Б");
  assert.equal(sizeText(1023), "1023 Б");
  assert.equal(sizeText(1024), "1,0 КБ");
  assert.equal(sizeText(12154), "11,9 КБ");
  assert.equal(sizeText(5 * 1024 * 1024), "5,0 МБ");
  assert.equal(sizeText("сміття"), "0 Б");
  assert.equal(sizeText(-5), "0 Б");
});

test("стеля запиту довіри довша за 120 с системного вікна сервера, але скінченна", () => {
  assert.ok(TRUST_POST_TIMEOUT_MS > 120000 && TRUST_POST_TIMEOUT_MS <= 180000, String(TRUST_POST_TIMEOUT_MS));
});

test("кожен клас tr-* розмітки має правило в styles.css", () => {
  const src = read("trust-view.js").replace(/\/\*[\s\S]*?\*\//g, "");
  const css = read("styles.css").replace(/\/\*[\s\S]*?\*\//g, "");
  const classes = new Set();
  for (const m of src.matchAll(/class="([^"]+)"/g)) for (const c of m[1].split(/\s+/)) if (/^tr-/.test(c)) classes.add(c);
  assert.ok(classes.size >= 12, `знайдено лише ${classes.size}: ${[...classes]}`);
  const missing = [...classes].filter((c) => !new RegExp(`\\.${c}(?![\\w-])`).test(css));
  assert.deepEqual(missing, [], `класи без правила: ${missing.join(", ")}`);
});

test("css: діалог ширший за типову форму, а правила для <p> стоять під `.tr` — `.cv-ask p` (0,1,1) інакше перебив би їхні розмір і колір", () => {
  const css = read("styles.css").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.match(css, /\.cv-ask--form:has\(\.tr\)\s*\{[^{}]*width:\s*560px/, "діалог довіри — 560px (під список файлів)");
  assert.match(css, /\.cv-ask button\.tr-untrust\s*\{[^{}]*margin-right:\s*auto[^{}]*var\(--bad\)/, "«Забрати довіру» — ліворуч у рядку кнопок, небезпечна");
  const src = read("trust-view.js").replace(/\/\*[\s\S]*?\*\//g, "");
  const paragraphs = [...src.matchAll(/<p class="(tr-[\w-]+)"/g)].map((m) => m[1]);
  assert.ok(paragraphs.length >= 8, `абзаців знайдено лише ${paragraphs.length}: ${paragraphs}`);
  for (const cls of new Set(paragraphs)) {
    const sels = [...css.matchAll(/([^{}]+)\{[^{}]*\}/g)].flatMap((m) => m[1].split(",").map((x) => x.trim()))
      .filter((x) => new RegExp(`\\.${cls}(?![\\w-])`).test(x.split(/\s+/).pop()));
    assert.ok(sels.length, `для .${cls} нема правила`);
    for (const sel of sels) assert.match(sel, /^(\.tr|\.cv-ask--form) /, `«${sel}»: правило абзацу без префікса програє \`.cv-ask p\``);
  }
});

test("css (ревʼю Task 7): причина відмови читається на темній картці (--dim, етап В), довгі слова без пробілів переносяться, абзац попередження — --hi", () => {
  const css = read("styles.css").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.match(css, /\.tr-refused \.cn-why-detail\s*\{[^{}]*color:\s*var\(--dim\)/, "деталь відмови явно в --dim: на темній картці (етап В) токен читається, правило не мусить зникнути");
  const wrap = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter((m) => /overflow-wrap:\s*anywhere/.test(m[2])).map((m) => m[1].split(",").map((x) => x.trim()));
  for (const sel of [".tr .cv-form-h", ".tr-asks", ".tr .cv-form-err"]) {
    assert.ok(wrap.some((list) => list.includes(sel)), `«${sel}»: довге слово без пробілів розпирає діалог — потрібен overflow-wrap:anywhere`);
  }
  assert.match(css, /\.cv-ask--form \.tr-warn p\s*\{[^{}]*color:\s*var\(--hi\)/, "без кольору абзац бере --mid від `.cv-ask p`");
});

test("словник: кожен ключ, який кличе trust-view.js, є в обох мовах", () => {
  const code = read("trust-view.js").replace(/\/\*[\s\S]*?\*\//g, "");
  /* Ключі — і прямі `t("…")`, і ті, що обираються умовою (`t(x ? "trClose" : "askCancel")`): будь-який рядок вигляду
     імені ключа словника у лапках. */
  const keys = new Set([...code.matchAll(/\bt\("(\w+)"/g)].map((m) => m[1]));
  for (const m of code.matchAll(/"((?:tr|cn|ask)[A-Z]\w*)"/g)) keys.add(m[1]);
  assert.ok(keys.size >= 25, `зібрано лише ${keys.size}`);
  for (const k of ["trClose", "askCancel", "trNew", "trChanged", "trSecret", "trSecretPublic", "cnUntrust"]) assert.ok(keys.has(k), `не зібрано умовний ключ ${k}`);
  for (const k of keys) for (const lang of ["uk", "en"]) assert.ok(DICT[lang][k] !== undefined, `${lang}: немає «${k}»`);
});

/* M1 Task 2: інструменти в острівці й дії модуля — два рядки, лише коли непорожні. */
import { createHash } from "node:crypto";
const sha = (s) => createHash("sha256").update(s).digest("hex");

test("без tools/actions розмітка побайтово та сама, що до M1 (золоті відбитки)", () => {
  assert.equal(sha(trustDialogHTML(base())), "0e2daee73bb94252449c3430f194b391a6a32bd617e5791ad20c4b030a83480b");
  assert.equal(sha(trustDialogHTML(base({ state: "changed", record: true }))), "f68f403e42d6cdb133a0df8c40afab098b5255bd35a05987b9c3a56a67bd1a5b");
  assert.equal(sha(trustDialogHTML(base({ state: "refused", refused: { code: "x", detail: "d" } }))), "fcc9a5c9996bee509bdd9d181327f983772edaf22460a637e8f3fde92ce6d81d");
  const empty = trustDialogHTML(base({ tools: [], actions: [] }));
  assert.equal(sha(empty), "0e2daee73bb94252449c3430f194b391a6a32bd617e5791ad20c4b030a83480b");
  assert.equal(trustDialogHTML(base({ tools: "x", actions: null })), empty, "не-масиви — як порожні");
});

test("tools і actions: два рядки з підписами зі словника, назви через кому, між «Просить» і файлами", () => {
  const h = trustDialogHTML(base({ tools: [{ label: "Board", icon: "task" }, { label: "Notes", icon: "doc" }], actions: [{ label: "Go" }] }));
  assert.match(h, /<p class="tr-ext"><span class="tr-h3">Інструменти в острівці<\/span> Board, Notes<\/p>/);
  assert.match(h, /<p class="tr-ext"><span class="tr-h3">Дії<\/span> Go<\/p>/);
  assert.ok(h.indexOf("Site id") < h.indexOf("Інструменти в острівці") && h.indexOf("Дії<") < h.indexOf("Файли ("));
  const onlyActions = trustDialogHTML(base({ actions: [{ label: "Go" }] }));
  assert.doesNotMatch(onlyActions, /Інструменти в острівці/);
  assert.match(onlyActions, /Дії/);
  assert.doesNotMatch(trustDialogHTML(base({ tools: [{ label: "Board" }] })), /<span class="tr-h3">Дії/);
});

test("tools і actions: усе з диска екранується й обрізається до TR_MAX; у режимі refused рядків нема", () => {
  const h = trustDialogHTML(base({ tools: [{ label: "<b>x</b>" }], actions: [{ label: `<i>${"й".repeat(200)}` }] }));
  assert.match(h, /&lt;b&gt;x&lt;\/b&gt;/);
  assert.doesNotMatch(h, /<b>x<\/b>|<i>/);
  assert.match(h, /&lt;i&gt;й+…<\/p>/);
  const r = trustDialogHTML(base({ state: "refused", refused: { code: "x" }, tools: [{ label: "Board" }] }));
  assert.doesNotMatch(r, /Board|tr-ext/);
});

test("словник: trustTools і trustActions є в uk та en", () => {
  assert.equal(DICT.uk.trustTools, "Інструменти в острівці");
  assert.equal(DICT.uk.trustActions, "Дії");
  assert.equal(DICT.en.trustTools, "Island tools");
  assert.equal(DICT.en.trustActions, "Actions");
});

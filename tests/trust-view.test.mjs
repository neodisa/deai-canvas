/**
 * Діалог довіри своєму модулю (Deai 0.7.0, етап 3c; спека, «Діалог довіри»): розмітка `trustDialogHTML` для `askForm`
 * (контракт форми, фокус на «Скасувати», екранування всього з диска, обрізання до 80, позначки змін, режим `refused`),
 * `sizeText`, стеля запиту довіри, правила CSS і словник.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { DICT } from "../app/i18n.js";
import { TR_MAX, TRUST_POST_TIMEOUT_MS, sizeText, trustDialogHTML } from "../app/trust-view.js";

const read = (f) => readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
const base = (over = {}) => ({
  id: "acme", name: "Acme", version: "1.2", roles: ["publish"], path: "~/work/alpha/modules/acme",
  state: "untrusted", record: false, hash: "ab".repeat(32),
  settings: [{ key: "token", type: "secret", label: "Token", public: false }, { key: "site", type: "text", label: "Site id" }],
  files: [{ path: "module.json", size: 120, change: "new" }, { path: "server.py", size: 12034, change: "new" }],
  removed: [], total: { files: 2, bytes: 12154 }, ...over,
});

test("контракт askForm: один form-діалог, «Довіряю» — submit data-a=ok, «Скасувати» — data-a=cancel з ЄДИНИМ data-autofocus", () => {
  const h = trustDialogHTML(base());
  assert.equal((h.match(/<form/g) || []).length, 1);
  assert.match(h, /<form class="cv-form tr" novalidate role="dialog" aria-modal="true" aria-labelledby="tr-h">/);
  assert.match(h, /<h2 class="cv-form-h" id="tr-h">Довіритись модулю «Acme»\?<\/h2>/);
  assert.match(h, /<button type="submit" data-a="ok">Довіряю<\/button>/);
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
  assert.match(h, /class="tr-warn".*з вашими правами.*Після «Довіряю» система попросить/s);
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

test("refused: без «Довіряю» й попередження, причина і деталь, «Закрити» з фокусом; «Забрати довіру» — якщо запис є", () => {
  const h = trustDialogHTML({ id: "acme", name: "Acme", version: "1", roles: ["publish"], path: "~/m/acme", state: "refused",
    record: true, refused: { code: "symlink", detail: "alias.py: symbolic link" } });
  assert.doesNotMatch(h, /data-a="ok"|tr-warn|Відбиток|tr-files/);
  assert.match(h, /<p class="tr-refused" role="alert">.*Цій теці не можна довіритись\. У теці є символьне посилання\.<span class="cn-why-detail">alias\.py: symbolic link<\/span>/s);
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
  assert.match(css, /\.cv-ask button\.tr-untrust\s*\{[^{}]*margin-right:\s*auto[^{}]*var\(--bad-ink\)/, "«Забрати довіру» — ліворуч у рядку кнопок, небезпечна");
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

import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { ICONS, SPRITE, ico } from "../app/icons.js";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app");

test("спрайт віддає <symbol> з унікальним id на кожну іконку", () => {
  const names = Object.keys(ICONS);
  assert.ok(names.length >= 25, `іконок лише ${names.length}`);
  for (const n of names) {
    assert.match(ICONS[n], /^<symbol /, `«${n}» не symbol`);
    assert.ok(ICONS[n].includes(`id="i-${n}"`), `«${n}» без id="i-${n}"`);
  }
});

/* Найдешевша помилка іконочного набору — одрук в імені: `ico('inspekt')`
   малює порожнечу, а в темній смузі порожнечу помічають не одразу. Тому тест
   вичитує ВСІ виклики `ico('…')` з коду застосунку і звіряє зі спрайтом. */
test("кожне імʼя, яке кличе код, є у спрайті", () => {
  /* Перелік файлів ЗАБОРОННИЙ, а не дозвільний: беремо всі `app/*.js` і
     виключаємо лише сам `icons.js` (він набір ОГОЛОШУЄ, а не кличе).
     До 02.09.2026 тут стояли чотири файли іменами — і `ext-bar.js`
     (зовнішня смуга, План B) під охорону не потрапив, бо дописати його в
     список ніхто не мусив. Це вже третій укус того самого патерну в цьому
     проєкті: `i18n-literals.test.mjs` перевернув свою межу з тієї самої
     причини, а `i18n-keys.test.mjs` донині перевіряє лише один напрямок.
     Список, який треба доповнювати руками, забудуть. */
  const files = readdirSync(APP).filter((f) => f.endsWith(".js") && f !== "icons.js");
  const used = new Set();
  /* На момент написання цього тесту жодного виклику ico('…') у коді ще нема
     (Task 7 додасть перші) — тож used.size===0 зараз є ОЧІКУВАНИМ станом, а
     не ознакою зламаного регекспу, і копіювати ідею тесту i18n-keys.test.mjs
     буквально (безумовний `assert.ok(used.size > 0)`) тут не можна: він би
     червонів просто тому, що Task 7 ще не настав. Замість цього рахуємо
     виклики НЕЗАЛЕЖНИМ, простішим патерном (без вимоги лапок навколо імені)
     — і якщо він каже, що виклики вже Є, а «розумний» регексп із них не
     розпізнав жодного імені, це і є ознака зламаного регекспу: рядок
     `used.size > 0` нижче мусить бути ІСТИННИМ щоразу, коли `rawCalls > 0`. */
  let rawCalls = 0;
  for (const f of files) {
    let src;
    try { src = readFileSync(path.join(APP, f), "utf8"); } catch (e) { continue; }
    rawCalls += (src.match(/\bico\(/g) || []).length;
    for (const m of src.matchAll(/\bico\(\s*['"]([a-z0-9-]+)['"]/g)) used.add(m[1]);
  }
  assert.ok(
    rawCalls === 0 || used.size > 0,
    `код кличе ico(...) ${rawCalls} раз(и), але регексп не розпізнав жодного` +
      ` імені — регексп зламаний, а не викликів немає`
  );
  for (const n of used) {
    assert.ok(ICONS[n], `код кличе ico('${n}'), а у спрайті такої немає`);
  }
});

test("ico() віддає <svg> з <use> на потрібний symbol і заданим розміром", () => {
  const html = ico("page", 14);
  assert.match(html, /<svg[^>]*width="14"[^>]*height="14"/);
  assert.match(html, /<use href="#i-page"/);
  assert.match(html, /aria-hidden="true"/);
});

test("ico() з невідомим імʼям кидає, а не малює порожнечу", () => {
  assert.throws(() => ico("немаТакої"), /немаТакої/);
});

/* Спрайт — несуча конструкція: якщо контейнер `#sprite` або рядок, що його
   наповнює, зникнуть, порожніми стануть ОДРАЗУ ВСІ іконки оболонки, а не одна.
   Жоден наявний живий тест цього не бачить (вони чіпають `.cv-open` тільки на
   клік), тому перевірка статична — по вихідному тексту. Це слабше за живий
   DOM, і межа записана свідомо: тест ловить видалення й перейменування, але
   не побачить, якщо наповнення переїде в код, який не виконується. */
test("спрайт вставляється в документ: контейнер і наповнення на місці", () => {
  const html = readFileSync(path.join(APP, "index.html"), "utf8");
  assert.match(html, /<div id="sprite">/,
    "в index.html немає контейнера <div id=\"sprite\">");
  const app = readFileSync(path.join(APP, "app.js"), "utf8");
  assert.match(app, /getElementById\(['"]sprite['"]\)\.innerHTML\s*=\s*SPRITE/,
    "app.js не наповнює #sprite спрайтом");
});

/* SPRITE мусить нести ВСІ форми: інакше `ico()` віддасть <use> на symbol,
   якого в документі немає, і на місці іконки буде порожнеча без жодної
   помилки в консолі. */
test("SPRITE містить кожну іконку набору", () => {
  for (const n of Object.keys(ICONS)) {
    assert.ok(SPRITE.includes(`id="i-${n}"`), `у SPRITE немає «${n}»`);
  }
});

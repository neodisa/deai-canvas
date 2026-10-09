/**
 * Сторож проти повернення `prompt()`, `confirm()` і `alert()` у канвас.
 *
 * ЧОМУ їх тут не має бути — одне канонічне пояснення в шапці `app/ask.js`
 * (браузер уміє вимкнути всі три, і після галочки вони мовчки віддають
 * `null`/`false`/нічого, а код читає це як «користувач відмовився»). Тут лише
 * сторож; переказувати причину вдруге не будемо, бо копії розходяться.
 *
 * Окремим файлом, а не підтестом у `rows-model.test.mjs`, де він жив спершу:
 * до розбору рядів він стосунку не має, і знайти його там міг лише той, хто
 * знає історію комітів.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import test from "node:test";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app");

/* Стережеться КЛАС, а не сьогоднішнє написання, тому в регексі три рішення.
   Виклик, а не слово: у коментарях ці імена згадують як пояснення, ЧОМУ їх
   прибрали, а сторож, який забороняє пояснення, приберуть при першій же
   незручності — тому з-під нього виведено backtick (цитати коду цей проєкт
   пише саме так, шапка `app/ask.js` — не один раз), а виклику з backtick перед
   іменем у валідному JS не буває.
   `window.` / `globalThis.` / `self.` — те саме вікно й та сама тиха відмова, і
   це найімовірніше написання при поверненні: голий глобал у коді виглядає
   підозріло, а `window.confirm()` — ні.
   А от чужий `щось.alert(...)` виведено навмисно: це вже не примітив браузера,
   а метод, і забороняти імʼя методу цього сторожа не наймали. */
const call = (name) =>
  new RegExp(String.raw`(?<![\w.\`])(?:(?:window|globalThis|self)\.)?${name}\s*\(`, "g");

test("у канвасі не лишилось діалогів браузера — примітивів з тихим відмовленням", () => {
  /* ГЛОБ по всіх модулях канваса, а не один файл. Сторож на самому `app/app.js`
     ревʼю обійшло за один рядок: `export const legacy = () => prompt("назва?")`
     дописали в `app/ask.js` — модуль, який існує рівно щоб цей примітив
     замінити, — і прогін лишився зеленим. Найризикованіший файл був поза
     областю саме тому, що про нього ніхто не подумав.
     `readdirSync` без рекурсії — навмисно: `app/vendor/` це чужий код
     (comment-layer, інспектор), його ми не пишемо й не правимо, а
     `alert`-и всередині мініфікованого бандла зробили б сторожа вічно
     червоним і його тут-таки вимкнули б. */
  const files = readdirSync(APP).filter((f) => f.endsWith(".js")).sort();
  /* Без цього рядка сторож стереже порожнечу: помилка в шляху (перейменували
     теку, переїхав тест) дала б порожній перелік і вічно зелену перевірку. */
  assert.ok(files.length >= 8,
    `модулів канваса знайдено ${files.length} — глоб дивиться не туди: ${APP}`);

  const found = [];
  for (const f of files) {
    const src = readFileSync(path.join(APP, f), "utf8");
    for (const name of ["prompt", "confirm", "alert"]) {
      for (const hit of src.match(call(name)) ?? []) found.push(`${f}: ${hit}`);
    }
  }
  assert.deepEqual(found, [], "у канвасі лишились виклики діалогів браузера; якщо це "
    + "згадка в коментарі — цитуй її в backticks: `prompt()`. Заміна — `app/ask.js`: "
    + "`ask` замість `prompt`, `askYesNo` замість `confirm`, `tell` замість `alert`");
});

/* B4: `askChoice` — діалогу з вибором немає чим запустити без DOM, тож
   стережемо його склад по джерелу: те, що ламається тихо (кнопка «Гаразд» у
   виборі, відмова не `null`, список через innerHTML, фокус не на скасуванні). */
test("askChoice: експорт, відмова null, без «Гаразд», список через textContent, фокус на скасуванні", () => {
  const src = readFileSync(path.join(APP, "ask.js"), "utf8");
  assert.match(src, /export const askChoice\s*=/);
  assert.match(src, /kind === 'yesno' \? false : \(kind === 'tell' \? undefined : null\)/,
    "відмова для choice має лишитись null");
  assert.match(src, /kind === 'choice' \? null : button\('ok'/, "у choice кнопки «Гаразд» нема");
  assert.match(src, /cv-ask-list/);
  assert.match(src, /ul\.tabIndex = 0/, "прокручуваний список недосяжний з клавіатури");
  assert.match(src, /setAttribute\('role', 'list'\)/);
  assert.match(src, /aria-label/);
  assert.match(src, /li\.textContent = d/, "назви сторінок — чужий текст, не innerHTML");
  assert.doesNotMatch(src, /li\.innerHTML/);
  assert.match(src, /\(danger \|\| kind === 'choice'\) && no/, "фокус на «Скасувати»");
  assert.match(src, /done\(c\.a\)/);
  const css = readFileSync(path.join(APP, "styles.css"), "utf8");
  assert.match(css, /\.cv-ask-list\{[^}]*max-height:160px/);
  assert.match(css, /\.cv-ask button\.cv-ask-danger\{/);
});

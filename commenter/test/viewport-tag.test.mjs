/**
 * Ширина, на якій поставлено пін, мусить бути ВИДНА в картці коментаря.
 *
 * ЩО ЛАМАЛОСЬ (фідбек 03.09.2026, bf360). Коментар «цей список має бути
 * вертикально» був прочитаний як вимога на ВСІХ ширинах, хоча дизайнер дивився
 * мобільну версію — раунд правок пішов не туди. Дані були на місці від початку:
 * `meta.viewport` пишеться при створенні піна (`comment-layer.js`), бракувало
 * лише виводу. Інструментальну половину вже полагоджено (`bin/inbox.py` друкує
 * «ширина: мобільна · 390×844»), ця — про сам віджет.
 *
 * Межі ТІ САМІ, що в `bin/inbox.py` (768 і 1024) — розійдуться, і той самий пін
 * читатиметься як «планшет» в одному місці й «мобільна» в іншому.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)),
                         "..", "src", "comment-layer.js");
const src = readFileSync(SRC, "utf8");

/* Витягуємо чисту функцію з джерела: тягнути весь віджет у node неможливо
   (DOM), а межі ширини — саме чиста логіка, і саме вона мусить збігатися з
   Python-боком. */
/* Закривна дужка з ВІДСТУПОМ: функція живе всередині IIFE, тож `\n}` у
   колонці 0 стоїть за сотні рядків нижче — регексп без відступу вихоплював
   пів файлу і падав синтаксисом, а не перевіряв межі. */
const m = src.match(/ {2}function vpBand\([\s\S]*?\n {2}\}/);
assert.ok(m, "у comment-layer.js немає vpBand — ширину піна нема кому підписати");
// eslint-disable-next-line no-new-func
const vpBand = new Function(`${m[0]}; return vpBand;`)();

test_band("мобільна", [320, 390, 767]);
test_band("планшет", [768, 900, 1023]);
test_band("десктоп", [1024, 1280, 1920]);

function test_band(expected, widths) {
  for (const w of widths) {
    assert.equal(vpBand(w), expected, `${w}px мусить бути «${expected}»`);
  }
}

assert.equal(vpBand(undefined), "?", "невідома ширина не сміє прикидатись десктопом");
assert.equal(vpBand("не число"), "?");

/* Рядок мусить бути В РОЗМІТЦІ картки, а не лише у функції: без цього
   перевірка була б зелена і тоді, коли підпис ніде не малюється. */
assert.match(src, /class="vptag"/,
  "підпис ширини не потрапив у картку коментаря — функція є, виводу немає");

console.log("ok — ширина піна підписана, межі збігаються з bin/inbox.py");

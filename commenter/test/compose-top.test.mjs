/**
 * Композер не опускається під панель режимів (fb 05.11.2026).
 *
 * На рамці 978px пін на великий <section>: ні під елементом, ні над ним місця
 * нема, і форму притискало до низу вікна — під панель Element/Text/…, яка
 * лежить вище за z-index. `elementFromPoint` на кнопці «Comment» давав
 * `BUTTON.mode`: клік вмикав режим Text, коментар не відправлявся.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)),
                         "..", "src", "comment-layer.js");
const src = readFileSync(SRC, "utf8");
const m = src.match(/ {2}function composeTop\([\s\S]*?\n {2}\}/);
assert.ok(m, "у comment-layer.js немає composeTop");
// eslint-disable-next-line no-new-func
const composeTop = new Function(`${m[0]}\nreturn composeTop;`)();

const VIEW = 700, BOX = 170, BAR_TOP = 640;   // панель режимів: bottom 20px, ~40px заввишки
const floor = BAR_TOP - 8;

// Великий section на всю висоту: низ форми — над панеллю, не під нею.
{
  const top = composeTop({ top: -200, bottom: 1400 }, BOX, VIEW, floor);
  assert.ok(top + BOX <= floor, `форма (${top}…${top + BOX}) залазить під панель режимів (${BAR_TOP})`);
  assert.ok(top >= 12, "форма вилізла за верх вікна");
}

// Дрібний <p> — як і раніше: одразу під елементом.
assert.equal(composeTop({ top: 100, bottom: 130 }, BOX, VIEW, floor), 138);

// Під елементом місця до панелі нема — над ним.
assert.equal(composeTop({ top: 500, bottom: 520 }, BOX, VIEW, floor), 500 - BOX - 8);

// Панель прихована (floor = Infinity) — межа лише вікно.
assert.equal(composeTop({ top: -200, bottom: 1400 }, BOX, VIEW, Infinity), VIEW - 12 - BOX);

// Обидва композери ходять через composeTop і межу панелі.
const uses = src.match(/composeTop\([^;]*this\._composeFloor\(\)\)/g) || [];
assert.equal(uses.length, 2, `композерів через межу панелі: ${uses.length}, а мусить бути 2`);

console.log("compose-top: ok");

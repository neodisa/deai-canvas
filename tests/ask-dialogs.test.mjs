/**
 * Етап В (0.28.0): чисті шматки діалогів — заголовок/пояснення і місце поповера. Поведінку оболонки в браузері
 * покривають живі тести (`tests/live/feedback.test.mjs`, `update.test.mjs`, видалення — у файлах дерева й панелі).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { popPlace, splitTitle } from "../app/ask.js";

const src = readFileSync(new URL("../app/ask.js", import.meta.url), "utf8");

test("splitTitle: перший рядок — заголовок, решта — пояснення; краї обрізано, двокрапку в кінці заголовка прибрано", () => {
  assert.deepEqual(splitTitle("Видалити сторінку?\nТека зникне."), { title: "Видалити сторінку?", body: "Тека зникне." });
  assert.deepEqual(splitTitle("Вимкнути?\n\nТиша для всіх.\nДругий рядок.\n"), { title: "Вимкнути?", body: "Тиша для всіх.\nДругий рядок." });
  assert.deepEqual(splitTitle("Нова назва сторінки:"), { title: "Нова назва сторінки", body: "" });
  assert.deepEqual(splitTitle(""), { title: "", body: "" });
  assert.deepEqual(splitTitle(null), { title: "", body: "" });
});

test("popPlace: по центру якоря, не ближче 8 px до країв; хвостик — на центр якоря", () => {
  const a = { left: 600, top: 700, width: 36, height: 36, bottom: 736 };
  assert.deepEqual(popPlace(a, 360, 400, 1200, 800, "above"), { left: 438, top: 290, tip: 180, place: "above" });
  const edge = { left: 1180, top: 40, width: 30, height: 24, bottom: 64 };
  assert.deepEqual(popPlace(edge, 340, 300, 1200, 800, "below"), { left: 852, top: 74, tip: 328, place: "below" });
});

test("popPlace: не влазить згори — перевертається вниз, і навпаки; коли ніде — притискається до краю", () => {
  const top = { left: 100, top: 30, width: 36, height: 36, bottom: 66 };
  assert.equal(popPlace(top, 300, 200, 1200, 800, "above").place, "below");
  const bottom = { left: 100, top: 760, width: 36, height: 30, bottom: 790 };
  assert.equal(popPlace(bottom, 300, 200, 1200, 800, "below").place, "above");
  const tiny = popPlace(top, 300, 900, 1200, 800, "above");
  assert.equal(tiny.top, 8);
});

test("ask.js тягне лише i18n.js (його везе й публічне превʼю)", () => {
  const imports = [...src.matchAll(/^import .* from ["']([^"']+)["'];?$/gm)].map((m) => m[1]);
  assert.deepEqual(imports, ["./i18n.js"]);
});

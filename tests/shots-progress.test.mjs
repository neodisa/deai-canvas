import assert from "node:assert/strict";
import test from "node:test";

import { PROGRESS_MARK, progressLine } from "../bin/shots-progress.mjs";

test("рядок події = маркер + JSON + перенос", () => {
  const line = progressLine({ ev: "frame", i: 3, total: 8, key: "poshuk" });
  assert.ok(line.startsWith(PROGRESS_MARK), "мусить починатись маркером");
  assert.ok(line.endsWith("\n"), "мусить закінчуватись переносом — читач бере порядково");
  assert.deepEqual(JSON.parse(line.slice(PROGRESS_MARK.length)),
                   { ev: "frame", i: 3, total: 8, key: "poshuk" });
});

/* Імена сторінок пише дизайнер, і в них буває перенос рядка. Читач бере stderr
   ПОРЯДКОВО, тож сирий `\n` усередині JSON розрізав би одну подію на дві —
   друга половина стала б сміттям без маркера й поїхала б у текст помилки. */
test("перенос усередині значення не розриває подію на два рядки", () => {
  const line = progressLine({ ev: "frame", name: "Пошук\nдругий рядок" });
  assert.equal(line.split("\n").length, 2, "рівно один перенос — фінальний");
  assert.equal(JSON.parse(line.slice(PROGRESS_MARK.length)).name, "Пошук\nдругий рядок");
});

test("маркер закінчується пробілом — інакше JSON злипся б з ним", () => {
  assert.ok(PROGRESS_MARK.endsWith(" "));
});

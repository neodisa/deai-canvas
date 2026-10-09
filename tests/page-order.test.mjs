import assert from "node:assert/strict";
import test from "node:test";

import { canMove, siblingsOf } from "../app/page-order.js";

/* Дерево як у `/api/iteration-pages`: верхній рівень + діти одного батька. */
const PAGES = [
  { id: "a" }, { id: "b", children: [{ id: "b1" }, { id: "b2" }, { id: "b3" }] },
  { id: "c" }, { id: "d" },
];

test("«Підняти/Опустити» не обіцяють руху за край", () => {
  assert.equal(canMove(PAGES, "a", -1), false);
  assert.equal(canMove(PAGES, "a", 1), true);
  assert.equal(canMove(PAGES, "d", 1), false);
  assert.equal(canMove(PAGES, "b3", 1), false, "остання дитина не стрибає до сусіда батька");
  assert.equal(canMove(PAGES, "b1", -1), false);
  assert.equal(canMove(PAGES, "nope", 1), false);
  assert.deepEqual(siblingsOf(PAGES, "b2"), { parent: "b", ids: ["b1", "b2", "b3"] });
});

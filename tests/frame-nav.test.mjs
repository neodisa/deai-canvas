import assert from "node:assert/strict";
import test from "node:test";

import { assetsPageOf } from "../app/frame-nav.js";

const PAGES = [
  { id: "main", name: "Головна" },
  { id: "holovna", name: "Головна", children: [{ id: "st", name: "Стан", kind: "state" }] },
  { id: "grp", name: "Тека", kind: "folder", children: [{ id: "inner", name: "Вкладена" }] },
  { id: "my page", name: "Пробіл" },
];

test("збіг: <id>/index.html і <id>/", () => {
  assert.equal(assetsPageOf("/it-assets/it1/holovna/index.html", "it1", PAGES), "holovna");
  assert.equal(assetsPageOf("/it-assets/it1/holovna/", "it1", PAGES), "holovna");
  assert.equal(assetsPageOf("/it-assets/it1/inner/index.html", "it1", PAGES), "inner");
});

test("неявна main: корінь ітерації", () => {
  assert.equal(assetsPageOf("/it-assets/it1/index.html", "it1", PAGES), "main");
  assert.equal(assetsPageOf("/it-assets/it1/", "it1", PAGES), "main");
});

test("інша ітерація, невідомий id, тека й стан — null", () => {
  assert.equal(assetsPageOf("/it-assets/it2/holovna/index.html", "it1", PAGES), null);
  assert.equal(assetsPageOf("/it-assets/it1/nope/index.html", "it1", PAGES), null);
  assert.equal(assetsPageOf("/it-assets/it1/grp/index.html", "it1", PAGES), null);
  assert.equal(assetsPageOf("/it-assets/it1/st/index.html", "it1", PAGES), null);
});

test("закодований сегмент декодується", () => {
  assert.equal(assetsPageOf("/it-assets/it1/my%20page/index.html", "it1", PAGES), "my page");
});

test("зламане кодування й зайва глибина — null", () => {
  assert.equal(assetsPageOf("/it-assets/it1/holovna%E0%A4%A/index.html", "it1", PAGES), null);
  assert.equal(assetsPageOf("/it-assets/it1/holovna/x/index.html", "it1", PAGES), null);
  assert.equal(assetsPageOf("/it-assets/it1/holovna/style.css", "it1", PAGES), null);
  assert.equal(assetsPageOf("/commented", "it1", PAGES), null);
  assert.equal(assetsPageOf("/it-assets/it1/holovna/index.html", "it1", null), null);
});

import { followDecision, hashFor } from "../app/frame-nav.js";

test("followDecision: до 3 переходів за 3 с дозволено, четвертий — ні, вікно зсувається", () => {
  let st = [];
  for (const now of [0, 100, 200]) {
    const d = followDecision(st, now);
    assert.equal(d.follow, true);
    st = d.stamps;
  }
  const d4 = followDecision(st, 300);
  assert.equal(d4.follow, false);
  assert.equal(followDecision(d4.stamps, 3500).follow, true, "після вікна знову можна");
  assert.deepEqual(followDecision([], 5).stamps, [5]);
});

test("hashFor: хвіст лише для тієї самої ітерації й сторінки", () => {
  const p = { it: "it1", page: "poshuk", hash: "#sec" };
  assert.equal(hashFor(p, "it1", "poshuk"), "#sec");
  assert.equal(hashFor(p, "it1", "holovna"), "");
  assert.equal(hashFor(p, "it2", "poshuk"), "");
  assert.equal(hashFor(null, "it1", "poshuk"), "");
});

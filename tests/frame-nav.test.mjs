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

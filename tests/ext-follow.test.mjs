import assert from "node:assert/strict";
import test from "node:test";

import { followPageOf } from "../app/ext-follow.js";

const PAGES = [
  { id: "it1/holovna", it: "it1", path: "it1/holovna/index.html" },
  { id: "it1/poshuk", it: "it1", path: "it1/poshuk/index.html" },
  { id: "it2/holovna", it: "it2", path: "it2/holovna/index.html" },
  { id: "it1/my page", it: "it1", path: "it1/my page/index.html" },
  { id: "it1/папка", it: "it1", path: "it1/папка/index.html" },
];

test("та сама ітерація: шлях рамки веде на сторінку (обгортка в корені)", () => {
  assert.equal(followPageOf("/it1/poshuk/index.html", "/", PAGES, "it1"), "it1/poshuk");
  assert.equal(followPageOf("/it1/poshuk/index.html", "/index.html", PAGES, "it1"), "it1/poshuk");
});

test("форма з кінцевим слешем: <dir>/ = <dir>/index.html", () => {
  assert.equal(followPageOf("/it1/poshuk/", "/", PAGES, "it1"), "it1/poshuk");
});

test("обгортка у вкладеній теці (pv-…/): базу береться від шляху обгортки", () => {
  assert.equal(followPageOf("/pv-1/it1/poshuk/index.html", "/pv-1/index.html", PAGES, "it1"), "it1/poshuk");
  assert.equal(followPageOf("/pv-1/it1/poshuk/index.html", "/pv-1/", PAGES, "it1"), "it1/poshuk");
  assert.equal(followPageOf("/it1/poshuk/index.html", "/pv-1/index.html", PAGES, "it1"), null, "поза базою обгортки");
  assert.equal(followPageOf("/xx-1/it1/poshuk/index.html", "/pv-1/index.html", PAGES, "it1"), null, "чужа тека тієї ж довжини");
});

test("інша ітерація — null", () => {
  assert.equal(followPageOf("/it2/holovna/index.html", "/", PAGES, "it1"), null);
  assert.equal(followPageOf("/it2/holovna/index.html", "/", PAGES, "it2"), "it2/holovna");
});

test("невідомий шлях, не index.html, зовнішній — null", () => {
  assert.equal(followPageOf("/it1/nope/index.html", "/", PAGES, "it1"), null);
  assert.equal(followPageOf("/it1/poshuk/other.html", "/", PAGES, "it1"), null);
  assert.equal(followPageOf("/it1/poshuk", "/", PAGES, "it1"), null);
  assert.equal(followPageOf("/shell/i18n.js", "/", PAGES, "it1"), null);
  assert.equal(followPageOf("", "/", PAGES, "it1"), null);
  assert.equal(followPageOf(null, "/", PAGES, "it1"), null);
  assert.equal(followPageOf("/it1/poshuk/index.html", "/", PAGES, ""), null);
  assert.equal(followPageOf("/it1/poshuk/index.html", "/", null, "it1"), null);
});

test("закодовані імена (пробіл, кирилиця) збігаються; зламане кодування — null", () => {
  assert.equal(followPageOf("/it1/my%20page/index.html", "/", PAGES, "it1"), "it1/my page");
  assert.equal(followPageOf("/it1/%D0%BF%D0%B0%D0%BF%D0%BA%D0%B0/index.html", "/", PAGES, "it1"), "it1/папка");
  assert.equal(followPageOf("/it1/%E0%A4%A/index.html", "/", PAGES, "it1"), null);
});

test("query і hash не входять у шлях і нічого не міняють", () => {
  assert.equal(followPageOf("/it1/poshuk/index.html?x=1#y", "/", PAGES, "it1"), "it1/poshuk");
});

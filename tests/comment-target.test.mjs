import assert from "node:assert/strict";
import test from "node:test";
import { commentTarget } from "../app/comment-target.js";

const c = (meta) => ({ id: "x", meta });

test("тег «<n>/<сторінка>» → ітерація й сторінка", () => {
  assert.deepEqual(commentTarget(c({ version: "28/media-verified--none" })), { it: "it28", page: "media-verified--none" });
  assert.deepEqual(commentTarget(c({ version: "27/media-filter-tags" })), { it: "it27", page: "media-filter-tags" });
});

test("тег «<n>» → головна сторінка main", () => {
  assert.deepEqual(commentTarget(c({ version: "27" })), { it: "it27", page: "main" });
  assert.deepEqual(commentTarget(c({ version: 3 })), { it: "it3", page: "main" });
});

test("legacy-тег «it1» теж розбирається", () => {
  assert.deepEqual(commentTarget(c({ version: "it1" })), { it: "it1", page: "main" });
});

test("без тегу — за маршрутом", () => {
  assert.deepEqual(commentTarget(c({ route: "/it27/media-filter-tags/index.html" })), { it: "it27", page: "media-filter-tags" });
  assert.deepEqual(commentTarget(c({ route: "/it27/index.html" })), { it: "it27", page: "main" });
  assert.deepEqual(commentTarget(c({ route: "/it27/index.html#a?x=1" })), { it: "it27", page: "main" });
});

test("тег має перевагу над маршрутом", () => {
  assert.deepEqual(commentTarget(c({ version: "5/a", route: "/it9/b/index.html" })), { it: "it5", page: "a" });
});

test("нерозбірливе → null", () => {
  assert.equal(commentTarget(c({ route: "/commented" })), null);
  assert.equal(commentTarget(c({ version: "abc" })), null);
  assert.equal(commentTarget(c({})), null);
  assert.equal(commentTarget(c(null)), null);
  assert.equal(commentTarget(null), null);
  assert.equal(commentTarget(c({ version: "", route: "" })), null);
});

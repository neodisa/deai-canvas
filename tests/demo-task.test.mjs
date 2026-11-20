import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { demoFiles } from "../ops/demo-task/build.mjs";
import { DEMO_PINS } from "../ops/readme-shots/demo-pages.mjs";

/* Шаблон демо-задачі (0.33.0) — згенерований `node ops/demo-task.mjs`; тут — що копія в репо дорівнює генератору. */
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIR = path.join(ROOT, "app", "templates", "demo");
const walk = (d, pre = "") => readdirSync(d).flatMap((n) => (statSync(path.join(d, n)).isDirectory()
  ? walk(path.join(d, n), `${pre}${n}/`) : [`${pre}${n}`]));

test("шаблон демо == вихід генератора, файл у файл (інакше: node ops/demo-task.mjs)", () => {
  const want = demoFiles();
  assert.deepEqual(walk(DIR).sort(), Object.keys(want).sort());
  for (const [rel, text] of Object.entries(want)) assert.equal(readFileSync(path.join(DIR, rel), "utf8"), text, rel);
});

test("шаблон: корінь переадресовує на першу сторінку; pages.json і флоу називають лише наявні сторінки", () => {
  const files = demoFiles();
  assert.match(files["index.html"], /url=dashboard\//);
  const ids = [];
  const walkTree = (list) => { for (const p of list) { if (p.kind !== "folder") ids.push(p.id); walkTree(p.children || []); } };
  walkTree(JSON.parse(files["pages.json"]).pages);
  assert.ok(ids.length >= 7, "5 сторінок і 2 стани");
  for (const id of ids) assert.ok(files[`${id}/index.html`], `немає теки сторінки ${id}`);
  for (const n of JSON.parse(files["flow.json"]).flows[0].nodes) assert.ok(ids.includes(n.page), n.page);
});

test("піни демо: відкритий і закритий з поясненням; сторінка є; відбиток є", () => {
  const data = JSON.parse(readFileSync(path.join(ROOT, "app", "templates", "demo-pins.json"), "utf8"));
  assert.deepEqual(data.pins.map((p) => [p.page, p.sel, p.status]), DEMO_PINS.map((p) => [p.page, p.sel, p.status]));
  assert.deepEqual(data.pins.map((p) => p.status).sort(), ["open", "resolved"]);
  for (const p of data.pins) {
    assert.ok(p.fp && typeof p.fp === "object", `відбиток ${p.sel}`);
    assert.ok(existsSync(path.join(DIR, p.page, "index.html")), p.page);
  }
  assert.ok(data.pins.find((p) => p.status === "resolved").reason);
});

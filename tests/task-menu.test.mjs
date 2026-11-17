import assert from "node:assert/strict";
import test from "node:test";
import { setLang } from "../app/i18n.js";
import { taskMenuHTML, taskMenuItems } from "../app/task-menu.js";

setLang("uk");

test("меню «Моїх»: перейменувати, мітки, (превʼю), видалити — у цьому порядку; превʼю лише з http(s)", () => {
  const ths = (x) => taskMenuItems(x).filter((i) => i !== "sep").map((i) => i.th);
  assert.deepEqual(ths({ id: "a", published: null }), ["rename", "tags", "delete"]);
  assert.deepEqual(ths({ id: "a", published: "https://p.example/a" }), ["rename", "tags", "preview", "delete"]);
  assert.deepEqual(ths({ id: "a", published: "javascript:alert(1)" }), ["rename", "tags", "delete"]);
});

test("меню кошика: повернути, видалити назавжди", () => {
  assert.deepEqual(taskMenuItems({ id: "a" }, { trash: true }).filter((i) => i !== "sep").map((i) => i.th),
    ["restore", "purge"]);
});

test("розмітка: role=menu, пункти menuitem з data-th і data-id, клавіші, небезпечний пункт, id екрановано", () => {
  const h = taskMenuHTML({ id: 'x"><b>', published: "https://p.example/x" });
  assert.match(h, /^<div id="th-menu" class="cv-ctx th-menu" role="menu"/);
  assert.equal((h.match(/role="menuitem"/g) || []).length, 4);
  assert.match(h, /data-th="rename"[^>]*>.*F2/s);
  assert.match(h, /class="danger"[^>]*data-th="delete"|data-th="delete"[^>]*class="danger"/);
  assert.match(h, /<a [^>]*data-th="preview"[^>]*href="https:\/\/p\.example\/x"[^>]*target="_blank"/);
  assert.ok(!h.includes('"><b>'), "id мусить бути екранований");
});

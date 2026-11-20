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

test("розмітка меню кошика: «Повернути» і «Видалити назавжди» (небезпечний), без превʼю", () => {
  const h = taskMenuHTML({ id: "old", published: "https://p.example/x" }, { trash: true });
  assert.equal((h.match(/role="menuitem"/g) || []).length, 2);
  assert.match(h, /data-th="restore" data-id="old"/);
  assert.match(h, /class="danger"[^>]*data-th="purge"/);
  assert.ok(!h.includes('data-th="preview"'));
});

const GOLDEN_PLAIN = "<div id=\"th-menu\" class=\"cv-ctx th-menu\" role=\"menu\" aria-label=\"Дії задачі t1\"><button type=\"button\" role=\"menuitem\" tabindex=\"-1\" data-th=\"rename\" data-id=\"t1\"><svg class=\"ico\" width=\"15\" height=\"15\" aria-hidden=\"true\"><use href=\"#i-pencil\"/></svg><span>Перейменувати</span><kbd>F2</kbd></button><button type=\"button\" role=\"menuitem\" tabindex=\"-1\" data-th=\"tags\" data-id=\"t1\"><svg class=\"ico\" width=\"15\" height=\"15\" aria-hidden=\"true\"><use href=\"#i-sliders\"/></svg><span>Мітки…</span></button><hr role=\"separator\"><button type=\"button\" role=\"menuitem\" tabindex=\"-1\" class=\"danger\" data-th=\"delete\" data-id=\"t1\"><svg class=\"ico\" width=\"15\" height=\"15\" aria-hidden=\"true\"><use href=\"#i-trash\"/></svg><span>Видалити</span><kbd>⌫</kbd></button></div>";

test("золотий: без дій модулів розмітка байт у байт як раніше", () => {
  assert.equal(taskMenuHTML({ id: "t1" }), GOLDEN_PLAIN);
  assert.equal(taskMenuHTML({ id: "t1" }, { actions: [] }), GOLDEN_PLAIN);
});

test("дії модулів: перед «Видалити», роздільник, data-th=modact + data-v, підпис екранований; у кошику їх нема", () => {
  const actions = [{ key: "m/a", label: 'P"<b>', module: "m", id: "a", moduleName: "M" }];
  const h = taskMenuHTML({ id: "t1" }, { actions });
  assert.match(h, /data-th="modact" data-id="t1" data-v="m\/a"/);
  assert.ok(h.includes("<span>P&quot;&lt;b&gt;</span>") && !h.includes("<b>"));
  assert.ok(h.indexOf('data-th="tags"') < h.indexOf('data-th="modact"') && h.indexOf('data-th="modact"') < h.indexOf('data-th="delete"'));
  assert.equal(taskMenuHTML({ id: "t1" }, { trash: true, actions }), taskMenuHTML({ id: "t1" }, { trash: true }));
});

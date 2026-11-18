import assert from "node:assert/strict";
import test from "node:test";
import { setLang } from "../app/i18n.js";
import { tabsHTML } from "../app/tabs-view.js";

setLang("uk");
const vm = (over = {}) => ({
  logoOn: false, gearOn: false, update: null,
  items: [
    { id: "LIGA-1", title: "Картка <b>", color: "space-2", active: true, claude: "working" },
    { id: "LIGA-2", title: "", color: null, active: false, claude: null },
  ],
  ...over,
});

test("логотип, вкладки, «+», шестерня — у цьому порядку, з іменами дій", () => {
  const h = tabsHTML(vm());
  const acts = [...h.matchAll(/data-act="([a-z]+)"/g)].map((m) => m[1]);
  assert.deepEqual(acts, ["home", "tab", "tabclose", "tab", "tabclose", "tabnew", "settings"]);
});

test("активна вкладка — aria-current, решта — ні; назва екранована й лише в підказці", () => {
  const h = tabsHTML(vm());
  assert.match(h, /data-act="tab" data-val="LIGA-1"[^>]*aria-current="page"/);
  assert.doesNotMatch(h, /data-val="LIGA-2"[^>]*aria-current/);
  assert.ok(h.includes("Картка &lt;b&gt;"));
  assert.ok(!h.includes("<b>"));
});

test("колір простору — лише токен у style; без кольору — нейтральна крапка", () => {
  const h = tabsHTML(vm());
  assert.ok(h.includes("background:var(--space-2)"));
  assert.equal((h.match(/class="tab-dot"/g) || []).length, 2);
});

test("стан Claude — крапка з класом стану й іменем для читача", () => {
  const h = tabsHTML(vm());
  assert.match(h, /class="tab-claude tab-claude--working" role="img" aria-label="AI працює"/);
  assert.equal((h.match(/tab-claude--/g) || []).length, 1);
});

test("хрестик має імʼя з ідентифікатором задачі", () => {
  assert.ok(tabsHTML(vm()).includes('aria-label="Закрити вкладку LIGA-2"'));
});

test("логотип на «Задачах» і шестерня на «Налаштуваннях» — aria-current", () => {
  assert.match(tabsHTML(vm({ logoOn: true })), /data-act="home"[^>]*aria-current="page"/);
  assert.match(tabsHTML(vm({ gearOn: true })), /data-act="settings"[^>]*aria-current="page"/);
});

test("пігулка оновлення — лише коли є, перед шестернею", () => {
  assert.ok(!tabsHTML(vm()).includes('data-act="update"'));
  const h = tabsHTML(vm({ update: { version: "0.26.0", restart: false } }));
  assert.ok(h.indexOf('data-act="update"') < h.indexOf('data-act="settings"'));
});

test("вкладка з news: tab-news із числом і aria-label; без news — нема; 99+", () => {
  const h = tabsHTML(vm({ items: [
    { id: "LIGA-1", title: "", color: null, active: false, claude: null, news: 4 },
    { id: "LIGA-2", title: "", color: null, active: false, claude: null, news: 0 },
    { id: "LIGA-3", title: "", color: null, active: false, claude: null, news: 120 },
  ] }));
  assert.equal((h.match(/class="tab-news"/g) || []).length, 2);
  assert.match(h, /<span class="tab-news" role="img" aria-label="Нових командних коментарів: 4">4<\/span>/);
  assert.match(h, />99\+<\/span>/);
});

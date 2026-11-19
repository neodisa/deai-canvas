import assert from "node:assert/strict";
import test from "node:test";

import { setLang } from "../app/i18n.js";
import { catalogGroups } from "../app/catalog-model.js";
import { catFormHTML, catListHTML, catOwnHTML } from "../app/catalog-view.js";
import { modName } from "../app/connections-view.js";

const E = (id, roles, extra = {}) => ({ id, name: id, roles, builtin: true, enabled: false, status: "unchecked", settings: [], ...extra });
const LIST = [
  E("static-publish", ["publish"], { enabled: true }),
  E("vercel-publish", ["publish"]),
  E("git-sync", ["vcs"]),
  E("css-tokens", ["tokens"]),
];
const groups = () => catalogGroups(LIST, modName);

test.beforeEach(() => setLang("uk"));

test("сторінка 1: групи за ролями, рядок із назвою, описом і «Підключити» / «Замінити {поточний}»; останній — пунктирний «Свій модуль»", () => {
  const h = catListHTML(groups());
  assert.deepEqual([...h.matchAll(/<h3 class="cat-g">([^<]*)<\/h3>/g)].map((m) => m[1]), ["Публікація", "Синхронізація з git", "Токени дизайн-системи"]);
  assert.match(h, /<b>Vercel<\/b><span>Викладає превʼю[^<]*<\/span>[^]*?data-cat-pick="vercel-publish"[^>]*>Замінити Публікація в теку<\/button>/);
  assert.match(h, /data-cat-pick="git-sync"[^>]*>Підключити<\/button>/);
  assert.doesNotMatch(h, /data-cat-pick="static-publish"/, "увімкнений — не в каталозі");
  assert.match(h, /<div class="cat cat--own">[^]*?<b>Свій модуль<\/b><span>Агент напише модуль під вашу задачу; він житиме в теці простору\.<\/span>[^]*?data-cat-own[^>]*>Як додати/);
  assert.ok(h.lastIndexOf("cat--own") > h.lastIndexOf("data-cat-pick"), "«Свій модуль» — останній рядок");
});

test("сторінка 1: роль із пунктирної картки — `.cat--hl` на її рядках і `data-autofocus` на першій її кнопці; без ролі — автофокус на першому рядку", () => {
  const hl = catListHTML(groups(), "vcs");
  assert.equal((hl.match(/cat--hl/g) || []).length, 1);
  assert.match(hl, /class="cat cat--hl">[^]*?data-cat-pick="git-sync" data-autofocus>/);
  assert.equal((hl.match(/data-autofocus/g) || []).length, 1);
  const plain = catListHTML(groups());
  assert.doesNotMatch(plain, /cat--hl/);
  assert.match(plain, /data-cat-pick="vercel-publish" data-autofocus>/, "перша кнопка першого рядка, а не хрестик шапки");
  assert.doesNotMatch(catListHTML(groups(), "notify"), /cat--hl/, "роль без рядків — нічого не підсвічується");
  assert.match(catListHTML(groups(), "notify"), /data-cat-pick="vercel-publish" data-autofocus>/);
});

test("сторінка 1: порожній каталог — лише «Свій модуль», фокус на ньому", () => {
  const h = catListHTML([]);
  assert.doesNotMatch(h, /data-cat-pick|cat-g/);
  assert.match(h, /data-cat-own data-autofocus>/);
});

test("форма: шапка стала для обох сторінок (`«‹»` схований на першій, видно на другій; підпис — `Додати модуль` / `Свій модуль`)", () => {
  const f1 = catFormHTML("<i></i>", "list");
  assert.match(f1, /^<form class="cv-form cat-d" data-form="catalog" data-page="list" novalidate role="dialog" aria-modal="true" aria-labelledby="cat-h">/);
  assert.match(f1, /data-cat-back aria-label="Назад до каталогу" title="Назад до каталогу" hidden>/);
  assert.match(f1, /<h2 class="cv-form-h" id="cat-h">Додати модуль<\/h2>/);
  assert.match(f1, /<button type="button" class="icob" data-a="cancel" aria-label="Закрити"/, "хрестик — перший data-a=cancel");
  assert.match(f1, /<div class="cat-pg"><i><\/i><\/div><\/form>$/);
  const f2 = catFormHTML("", "own");
  assert.doesNotMatch(f2, /data-cat-back[^>]*hidden/);
  assert.match(f2, /id="cat-h">Свій модуль<\/h2>/);
  assert.equal((f1.match(/data-a="cancel"/g) || []).length, 1, "рівно один «Скасувати» у шапці: сторінки не додають вдруге");
});

test("сторінка 2: три кроки в `ol.steps`, поле #own-what, живий запит `pre.prompt`, «Скопіювати запит»; Закрити — data-a=cancel", () => {
  const h = catOwnHTML("Напиши <модуль> & «x»", "звіряти <кольори>");
  assert.match(h, /<ol class="steps"><li><b>Попросіть агента<\/b> — запит нижче;[^<]*<\/li><li><b>Модуль зʼявиться тут<\/b> з позначкою «Чекає довіри»\.<\/li><li><b>Перегляньте код і довірте<\/b> — підтвердьте в системному вікні\.<\/li><\/ol>/);
  assert.match(h, /<label for="own-what">Що має робити модуль<\/label><textarea class="ta" id="own-what" name="what"[^>]*placeholder="напр\. звіряти кольори макета з brand\.css"[^>]*>звіряти &lt;кольори&gt;<\/textarea>/);
  assert.match(h, /<pre class="prompt" id="own-prompt">Напиши &lt;модуль&gt; &amp; «x»<\/pre>/, "дані екрановані");
  assert.match(h, /<button type="button" class="ctl ctl--out" data-a="cancel">Закрити<\/button>/);
  assert.match(h, /data-cat-copy>[^]*?Скопіювати запит<\/button>/);
});

test("англійська: ті самі гачки, інші слова", () => {
  setLang("en");
  assert.match(catListHTML(groups()), /Replace Publish to folder|Replace /);
  assert.match(catListHTML(groups()), /data-cat-own[^>]*>How to add/);
  assert.match(catOwnHTML("p"), /Copy the request/);
  assert.match(catFormHTML("", "list"), /id="cat-h">Add a module</);
});

test("дані з маніфесту екрануються: назва чужого модуля й тримача ролі", () => {
  const list = [E("static-publish", ["publish"], { enabled: true, name: "<img onerror=x>" }), E("<b>evil</b>", ["publish"], { name: '"><script>' })];
  const h = catListHTML(catalogGroups(list, modName));
  assert.doesNotMatch(h, /<img|<script|<b>evil/);
  assert.match(h, /data-cat-pick="&lt;b&gt;evil&lt;\/b&gt;"/);
});

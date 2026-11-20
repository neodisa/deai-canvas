import assert from "node:assert/strict";
import test from "node:test";

import { setLang } from "../app/i18n.js";
import { generalBodyHTML, keysBodyHTML, updateBodyHTML } from "../app/app-settings-view.js";
import { KEYS, keysHTML } from "../app/shell-palette.js";

test.beforeEach(() => setLang("uk"));

const radios = (html) => [...html.matchAll(/<button[^>]*role="radio"[^>]*>/g)].map((m) => m[0]);

test("Загальне: мова — радіогрупа «Українська | English», вибрана одна, tabindex ходить із нею", () => {
  const uk = generalBodyHTML({ lang: "uk" });
  assert.match(uk, /role="radiogroup"/);
  const r = radios(uk);
  assert.equal(r.length, 2);
  assert.match(r[0], /data-v="uk"/); assert.match(r[0], /aria-checked="true"/); assert.match(r[0], /tabindex="0"/);
  assert.match(r[1], /data-v="en"/); assert.match(r[1], /aria-checked="false"/); assert.match(r[1], /tabindex="-1"/);
  assert.match(uk, />Українська</); assert.match(uk, />English</);
  const en = radios(generalBodyHTML({ lang: "en" }));
  assert.match(en[1], /aria-checked="true"/);
  assert.match(en[0], /aria-checked="false"/);
});

test("Загальне: «Окреме вікно» — «Встановити» лише коли можна, «Встановлено» у вікні застосунку, інакше рядка нема", () => {
  const none = generalBodyHTML({ lang: "uk", canInstall: false, standalone: false });
  assert.doesNotMatch(none, /Окреме вікно/);
  assert.doesNotMatch(none, /data-th="pwa"/);
  const can = generalBodyHTML({ lang: "uk", canInstall: true, standalone: false });
  assert.match(can, /Окреме вікно/);
  assert.match(can, /Deai Canvas як застосунок, без вкладок браузера/);
  assert.match(can, /data-th="pwa" data-v="install"[^>]*>.*Встановити</);
  const inst = generalBodyHTML({ lang: "uk", canInstall: true, standalone: true });
  assert.match(inst, /Встановлено/);
  assert.doesNotMatch(inst, /data-th="pwa"/);
});

test("Оновлення: назва з версією; стан із upSt_*; «остання перевірка»; кнопки за станами", () => {
  const ok = updateBodyHTML({ current: "0.30.2", latest: "0.30.2", available: false, state: "ok", checked_at: Math.floor(Date.now() / 1000) - 3600 * 3 });
  assert.match(ok, /Deai Canvas 0\.30\.2/);
  assert.match(ok, /остання перевірка 3 год тому/);
  assert.match(ok, /data-th="up" data-v="check"[^>]*>.*Перевірити зараз</);
  assert.doesNotMatch(ok, /data-v="open"/);
  assert.match(updateBodyHTML({ current: "0.30.2", state: "offline", checked_at: 1 }), /не можна дістатись|немає звʼязку з репозиторієм/);
  const avail = updateBodyHTML({ current: "0.30.2", latest: "0.31.0", available: true, state: "ok", checked_at: 1760000000 });
  assert.match(avail, /data-th="up" data-v="open"[^>]*>Оновити до 0\.31\.0</);
  const never = updateBodyHTML({ current: "0.30.2", available: false, state: null, checked_at: null });
  assert.doesNotMatch(never, /остання перевірка/);
  assert.doesNotMatch(updateBodyHTML(null), /undefined|null/);
});

test("Оновлення: перевірка у польоті — кнопка зайнята «Перевіряю…»", () => {
  const busy = updateBodyHTML({ current: "0.30.2" }, true);
  assert.match(busy, /data-v="check" disabled aria-busy="true"[^>]*>.*Перевіряю…</);
  assert.doesNotMatch(busy, /Перевірити зараз/);
});

test("Оновлення: англійською «Check now» / «Update to»", () => {
  setLang("en");
  assert.match(updateBodyHTML({ current: "1.0.0", latest: "1.1.0", available: true, state: "ok" }), /Check now[\s\S]*Update to 1\.1\.0/);
});

test("Гарячі клавіші: розділ містить кожну kbd із KEYS у групах, як аркуш `?`", () => {
  const html = keysBodyHTML();
  for (const k of KEYS) assert.ok(html.includes(`<kbd>${k.kbd}</kbd>`), `немає ${k.kbd}`);
  assert.equal((html.match(/<kbd>/g) || []).length, KEYS.length);
  assert.equal((html.match(/<h2 class="sub">/g) || []).length, 2);
  // той самий набір підписів і клавіш, що в аркуші
  const pairs = (h) => [...h.matchAll(/class="set-row-t">([^<]*)<\/span>.*?<kbd>([^<]*)<\/kbd>|<dt>([^<]*)<\/dt><dd><kbd>([^<]*)<\/kbd>/g)]
    .map((m) => [m[1] ?? m[3], m[2] ?? m[4]]);
  assert.deepEqual(pairs(html), pairs(keysHTML()));
});

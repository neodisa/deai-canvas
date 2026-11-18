/**
 * Статус Claude поза смугою (12.10.2026): острівець унизу і бейдж на іконці
 * застосунку. Модуль — чисті функції; проводка в `app.js`.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { ISLAND_SHELL, applyBadge, badgeFor, islandParts } from "../app/claude-status.js";
import { t } from "../app/i18n.js";

test("badgeFor: працює — крапка; чекає чи заблоковано — «1»; готово й тиша — нічого", () => {
  assert.equal(badgeFor({ state: "working" }), "dot");
  assert.equal(badgeFor({ state: "waiting" }), "one");
  assert.equal(badgeFor({ state: "blocked" }), "one");
  assert.equal(badgeFor({ state: "done" }), "none");
  assert.equal(badgeFor({ state: null }), "none");
  assert.equal(badgeFor(null), "none");
  assert.equal(badgeFor({ state: "щось-нове" }), "dot",
    "невідомий стан острівець показує як «працює» — бейдж мусить казати те саме");
});

function fakeNav() {
  const calls = [];
  return {
    calls,
    setAppBadge: (...a) => { calls.push(["set", ...a]); return Promise.resolve(); },
    clearAppBadge: () => { calls.push(["clear"]); return Promise.resolve(); },
  };
}

test("applyBadge: крапка — setAppBadge БЕЗ аргументу (0 бейдж знімає), «1» — setAppBadge(1), нічого — clearAppBadge", () => {
  const n = fakeNav();
  applyBadge(n, "dot");
  applyBadge(n, "one");
  applyBadge(n, "none");
  assert.deepEqual(n.calls, [["set"], ["set", 1], ["clear"]]);
});

test("applyBadge: без clearAppBadge «нічого» — setAppBadge(0), бо 0 за специфікацією знімає бейдж", () => {
  const calls = [];
  applyBadge({ setAppBadge: (...a) => { calls.push(["set", ...a]); return Promise.resolve(); } }, "none");
  assert.deepEqual(calls, [["set", 0]]);
});

test("applyBadge: немає API (вкладка, Firefox, Linux) чи API впав — тихо", async () => {
  assert.doesNotThrow(() => applyBadge({}, "dot"));
  assert.doesNotThrow(() => applyBadge(undefined, "dot"));
  assert.doesNotThrow(() => applyBadge({ setAppBadge() { throw new Error("sync"); } }, "one"));
  /* Справжній охоронець тут — сам `node:test`: відхилений проміс без обробника, що
     вилетів, поки тест чекає, валить ЦЕЙ тест (ревʼю 12.10.2026). Тому всі три
     шляхи й `await` до кінця тіку — «нічого» б'є найчастіше (кожен опит без удару). */
  const rejecting = { setAppBadge: () => Promise.reject(new Error("NotAllowed")),
    clearAppBadge: () => Promise.reject(new Error("NotAllowed")) };
  for (const k of ["dot", "one", "none"]) applyBadge(rejecting, k);
  await new Promise((r) => setTimeout(r, 20));
});

test("islandParts: серцебиття згасло чи ще не було — острівця немає", () => {
  assert.equal(islandParts(null), null);
  assert.equal(islandParts({ state: null }), null);
  assert.equal(islandParts(undefined), null);
});

test("islandParts: підписи станів; вік — лише в «працює»", () => {
  const w = islandParts({ state: "working", age_s: 20, note: "", phase: "design" });
  assert.equal(w.state, "working");
  assert.equal(w.label, t("claudeWorking"));
  assert.equal(w.age, "", "до хвилини секунд не показуємо");
  assert.equal(islandParts({ state: "working", age_s: 125 }).age, t("ageMin", 2));
  assert.equal(islandParts({ state: "working", age_s: 59 }).age, "", "межа хвилини");
  assert.equal(islandParts({ state: "working", age_s: 60 }).age, t("ageMin", 1), "межа хвилини");
  assert.equal(islandParts({ state: "working", age_s: -5 }).age, "", "годинник сервера назад");
  assert.equal(islandParts({ state: "working", age_s: Infinity }).age, "");
  const wt = islandParts({ state: "waiting", age_s: 400 });
  assert.equal(wt.label, t("claude_waiting"));
  assert.equal(wt.age, "");
  assert.equal(islandParts({ state: "blocked" }).label, t("claude_blocked"));
  assert.equal(islandParts({ state: "done" }).label, t("claude_done"));
  assert.equal(islandParts({ state: "щось-нове" }).state, "working");
});

test("islandParts: нотатка сервера не потрапляє в острівець — він клікопрозорий, підказка не показалась би", () => {
  const p = islandParts({ state: "working", age_s: 5, note: "Іт.2" });
  assert.deepEqual(Object.keys(p).sort(), ["age", "label", "state"], "зайве поле в частинах острівця");
  assert.ok(!p.label.includes("Іт.2") && !p.age.includes("Іт.2"));
});

test("ISLAND_SHELL: вік прихований від читача екрана, жива область — не тут", () => {
  assert.match(ISLAND_SHELL, /<span class="claude-age" aria-hidden="true"><\/span>/);
  assert.match(ISLAND_SHELL, /<span class="lbl-claude"><\/span>/);
  assert.match(ISLAND_SHELL, /<span class="claude-dot"><\/span>/);
  assert.ok(!/role=/.test(ISLAND_SHELL),
    "жива область — постійний #claude-hud; вузол, що перестворюється, оголошувався б щоразу");
});

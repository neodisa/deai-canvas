import assert from "node:assert/strict";
import test from "node:test";

import { catalogGroups, ownPrompt } from "../app/catalog-model.js";
import { DICT } from "../app/i18n.js";

const E = (id, roles, extra = {}) => ({ id, name: id.toUpperCase(), roles, builtin: true, enabled: false, status: "unchecked", ...extra });
const LIST = [
  E("css-tokens", ["tokens"]),
  E("git-sync", ["vcs"]),
  E("static-publish", ["publish"], { enabled: true, status: "ok" }),
  E("vercel-publish", ["publish"]),
  E("jira-tracker", ["tracker"]),
  E("supabase-comments", ["comments"]),
  E("mine", ["notify"], { builtin: false, custom: true }),
  E("gone", ["dashboard"], { status: "missing", enabled: true }),
];

test("catalogGroups: лише вимкнені вбудовані; увімкнений, свій і «не встановлений» — не в каталозі", () => {
  const ids = catalogGroups(LIST).flatMap((g) => g.rows.map((r) => r.id));
  assert.deepEqual(ids.sort(), ["css-tokens", "git-sync", "jira-tracker", "supabase-comments", "vercel-publish"]);
  for (const hidden of ["static-publish", "mine", "gone"]) assert.ok(!ids.includes(hidden), hidden);
});

test("catalogGroups: групи за ROLE_ORDER, не за порядком списку; порожніх груп нема", () => {
  assert.deepEqual(catalogGroups(LIST).map((g) => g.role), ["publish", "comments", "vcs", "tracker", "tokens"]);
});

test("catalogGroups: зайнята роль → replaces = назва тримача (через nameOf); вільна → null", () => {
  const g = catalogGroups(LIST, (e) => `«${e.name}»`);
  const row = (id) => g.flatMap((x) => x.rows).find((r) => r.id === id);
  assert.equal(row("vercel-publish").replaces, "«STATIC-PUBLISH»");
  assert.equal(row("git-sync").replaces, null);
  assert.equal(catalogGroups(LIST).flatMap((x) => x.rows).find((r) => r.id === "vercel-publish").replaces, "STATIC-PUBLISH", "типово — name запису");
});

test("catalogGroups: кілька тримачів — усі назви через кому; тримач-`missing` роль не тримає", () => {
  const list = [E("a", ["publish"]), E("b", ["publish"], { enabled: true }), E("c", ["publish"], { enabled: true }),
    E("d", ["vcs"]), E("x", ["vcs"], { enabled: true, status: "missing" })];
  const rows = Object.fromEntries(catalogGroups(list).flatMap((g) => g.rows).map((r) => [r.id, r.replaces]));
  assert.equal(rows.a, "B, C");
  assert.equal(rows.d, null);
});

test("catalogGroups: чужа роль — після відомих, без ролі — останньою; сміття у списку не кидає", () => {
  const list = [E("z", ["zeta"]), E("n", []), E("t", ["tokens"]), null, { id: 3 }, "x"];
  assert.deepEqual(catalogGroups(list).map((g) => g.role), ["tokens", "zeta", ""]);
  assert.deepEqual(catalogGroups(null), []);
  assert.deepEqual(catalogGroups([]), []);
});

test("ownPrompt: імʼя, тека, шлях до інструкції, що робити й заборона довіряти — обома мовами", () => {
  const a = { space: "Studio", folder: "/work/studio", authoring: "/opt/deai/docs/modules/authoring.md", what: "звіряти кольори" };
  const uk = ownPrompt({ ...a, lang: "uk" });
  for (const part of ["Studio", "/work/studio", "/opt/deai/docs/modules/authoring.md", "звіряти кольори", "modules/<id>/"]) {
    assert.ok(uk.includes(part), `uk: ${part}`);
  }
  assert.match(uk, /Довіряти модулю не намагайся/);
  const en = ownPrompt({ ...a, what: "compare colors", lang: "en" });
  for (const part of ["Studio", "/work/studio", "/opt/deai/docs/modules/authoring.md", "compare colors"]) assert.ok(en.includes(part), `en: ${part}`);
  assert.match(en, /Do not try to trust the module yourself/);
  assert.doesNotMatch(en, /Довіряти/);
});

test("ownPrompt: порожнє або пробільне `what` — нейтральна підстановка; невідома мова — українська", () => {
  for (const what of ["", "   ", undefined]) {
    const p = ownPrompt({ space: "S", folder: "/f", authoring: "/a.md", what, lang: "uk" });
    assert.ok(p.includes(DICT.uk.ownPromptWhat));
    assert.ok(!p.includes("undefined"));
  }
  assert.ok(ownPrompt({ space: "S", folder: "/f", authoring: "/a.md", what: "", lang: "en" }).includes(DICT.en.ownPromptWhat));
  assert.match(ownPrompt({ space: "S", lang: "de" }), /Напиши свій модуль/);
});

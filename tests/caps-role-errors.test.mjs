import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { setLang } from "../app/i18n.js";
import { connPageHTML } from "../app/connections-view.js";
import { providerLine, roleError, spaceJsonBad } from "../app/connections-model.js";

/* r15-1: `capabilities.error` читався як «space.json не читається» для БУДЬ-ЯКОГО коду, тож збій одного модуля (напр. git-sync)
   ховав усі картки «Підключення». Простір-рівневий — лише `space-json-unreadable`; збій ролі — `capabilities.errors[роль]`. */

const SP = (capabilities) => ({ id: "studio", name: "Studio", path: "/u/work/studio", capabilities });
const LIST = [
  { id: "git-sync", name: "Git", roles: ["vcs"], enabled: true, implicit: false, status: "error", settings: [] },
  { id: "vercel-publish", name: "Vercel", roles: ["publish"], enabled: true, implicit: false, status: "unchecked", settings: [] },
];
const view = (capabilities) => ({ space: SP(capabilities), list: LIST, failed: null, busy: new Map() });
const LOST_VCS = { publish: "vercel-publish", comments: null, vcs: null, dashboard: null, tracker: null, notify: null, tokens: null,
  error: "module-error", errors: { vcs: "module-error" } };

test.beforeEach(() => setLang("uk"));

test("spaceJsonBad: лише код space-json-unreadable; module-error, bad-manifest, порожнє, нема — ні", () => {
  assert.equal(spaceJsonBad({ error: "space-json-unreadable" }), true);
  for (const caps of [{ error: "module-error" }, { error: "bad-manifest" }, { error: "" }, {}, null, undefined, "x"]) {
    assert.equal(spaceJsonBad(caps), false, JSON.stringify(caps));
  }
});

test("roleError: код збою саме цієї ролі, інакше порожньо", () => {
  assert.equal(roleError(LOST_VCS, "vcs"), "module-error");
  assert.equal(roleError(LOST_VCS, "publish"), "");
  assert.equal(roleError({ error: "module-error" }, "vcs"), "", "старий сервер без errors — нічого не приписуємо ролі");
  assert.equal(roleError({ errors: { vcs: 7 } }, "vcs"), "");
  assert.equal(roleError(null, "vcs"), "");
});

test("providerLine: просторовий збій — error для всіх; збій ролі — лише її рядок", () => {
  assert.deepEqual(providerLine("publish", { publish: null, error: "space-json-unreadable" }, LIST), { kind: "error" });
  assert.deepEqual(providerLine("vcs", LOST_VCS, LIST), { kind: "roleError", code: "module-error" });
  assert.deepEqual(providerLine("publish", LOST_VCS, LIST), { kind: "module", id: "vercel-publish", entry: LIST[1] });
});

test("сторінка: збій модуля ролі НЕ ховає картки; нечитабельний space.json — ховає", () => {
  const ok = connPageHTML(view(LOST_VCS));
  assert.match(ok, /class="mc"/, "картки лишились");
  assert.doesNotMatch(ok, /space\.json цього простору не читається/);
  assert.doesNotMatch(ok, /cn-now|Зараз:/, "рядків «Зараз» на сторінці більше нема (етап Е)");
  assert.doesNotMatch(connPageHTML(view({ ...LOST_VCS, error: "space-json-unreadable", errors: undefined })), /class="mc"/);
});

test("майстер і сторінка читають просторовий збій через spaceJsonBad, а не сире capabilities.error", () => {
  const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<![:'"`])\/\/[^\n]*/g, "");
  for (const f of ["wizard.js", "connections-view.js"]) {
    const src = strip(readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8"));
    assert.match(src, /spaceJsonBad\(/, `${f} вирішує через spaceJsonBad`);
    assert.doesNotMatch(src, /capabilities\?\.error/, `${f} не читає сире capabilities?.error`);
  }
});

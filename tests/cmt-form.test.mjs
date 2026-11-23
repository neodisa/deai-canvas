/** Вигляд і мова форми коментатора (0.35): що оболонка віддає в `host.theme` / `host.labels`. */
import assert from "node:assert/strict";
import test from "node:test";

import { CMT_THEME_KEYS, cmtLabels, cmtTheme } from "../app/cmt-form.js";
import { DICT, t } from "../app/i18n.js";

test("cmtTheme: лише відомі токени, обрізані; порожні пропущено", () => {
  const vars = { "--s2": " rgb(1, 2, 3) ", "--sel": "", "--bogus": "x" };
  assert.deepEqual(cmtTheme({ getPropertyValue: (k) => vars[k] ?? "" }), { s2: "rgb(1, 2, 3)" });
  assert.ok(CMT_THEME_KEYS.includes("on-sel") && CMT_THEME_KEYS.includes("sel-tint-2") && !CMT_THEME_KEYS.includes("s0"));
});

test("cmtLabels: усі вісім підписів є в обох мовах, шаблони зі своїми токенами", () => {
  const seen = Object.keys(cmtLabels((k) => k)).sort();
  assert.deepEqual(seen, ["area", "cancel", "clear", "multiTitle", "placeholder", "quote", "submit", "target"]);
  for (const lang of ["uk", "en"]) {
    for (const k of ["cmtFormPh", "cmtFormCancel", "cmtFormSubmit", "cmtFormTarget", "cmtFormQuote", "cmtFormArea", "cmtFormMulti", "cmtFormClear"]) {
      assert.equal(typeof DICT[lang][k], "string", `${lang}.${k}`);
    }
    assert.match(DICT[lang].cmtFormTarget, /\{tag\}.*\{text\}/);
    assert.match(DICT[lang].cmtFormQuote, /\{text\}/);
    assert.match(DICT[lang].cmtFormArea, /\{target\}/);
    assert.match(DICT[lang].cmtFormMulti, /\{n\}/);
  }
  assert.equal(cmtLabels(t).placeholder, "Що змінити?");
});

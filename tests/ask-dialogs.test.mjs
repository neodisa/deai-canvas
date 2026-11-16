/**
 * Етап В (0.28.0): чисті шматки діалогів — заголовок/пояснення і місце поповера. Поведінку оболонки в браузері
 * покривають живі тести (`tests/live/feedback.test.mjs`, `update.test.mjs`, видалення — у файлах дерева й панелі).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { popPlace, splitTitle } from "../app/ask.js";

const src = readFileSync(new URL("../app/ask.js", import.meta.url), "utf8");

test("splitTitle: перший рядок — заголовок, решта — пояснення; краї обрізано, двокрапку в кінці заголовка прибрано", () => {
  assert.deepEqual(splitTitle("Видалити сторінку?\nТека зникне."), { title: "Видалити сторінку?", body: "Тека зникне." });
  assert.deepEqual(splitTitle("Вимкнути?\n\nТиша для всіх.\nДругий рядок.\n"), { title: "Вимкнути?", body: "Тиша для всіх.\nДругий рядок." });
  assert.deepEqual(splitTitle("Нова назва сторінки:"), { title: "Нова назва сторінки", body: "" });
  assert.deepEqual(splitTitle(""), { title: "", body: "" });
  assert.deepEqual(splitTitle(null), { title: "", body: "" });
});

test("popPlace: по центру якоря, не ближче 8 px до країв; хвостик — на центр якоря", () => {
  const a = { left: 600, top: 700, width: 36, height: 36, bottom: 736 };
  assert.deepEqual(popPlace(a, 360, 400, 1200, 800, "above"), { left: 438, top: 290, tip: 180, place: "above" });
  const edge = { left: 1180, top: 40, width: 30, height: 24, bottom: 64 };
  assert.deepEqual(popPlace(edge, 340, 300, 1200, 800, "below"), { left: 852, top: 74, tip: 328, place: "below" });
});

test("popPlace: не влазить згори — перевертається вниз, і навпаки; коли ніде — притискається до краю", () => {
  const top = { left: 100, top: 30, width: 36, height: 36, bottom: 66 };
  assert.equal(popPlace(top, 300, 200, 1200, 800, "above").place, "below");
  const bottom = { left: 100, top: 760, width: 36, height: 30, bottom: 790 };
  assert.equal(popPlace(bottom, 300, 200, 1200, 800, "below").place, "above");
  const tiny = popPlace(top, 300, 900, 1200, 800, "above");
  assert.equal(tiny.top, 8);
});

test("ask.js тягне лише i18n.js (його везе й публічне превʼю)", () => {
  const imports = [...src.matchAll(/^import .* from ["']([^"']+)["'];?$/gm)].map((m) => m[1]);
  assert.deepEqual(imports, ["./i18n.js"]);
});

import { tellError } from "../app/ask.js";

test("заголовок — h2.cv-ask-title з id, пояснення — p.cv-ask-text; поле підписане заголовком", () => {
  assert.match(src, /createElement\('h2'\)/);
  assert.match(src, /className = 'cv-ask-title'/);
  assert.match(src, /className = 'cv-ask-text'/);
  assert.match(src, /setAttribute\('aria-labelledby', TITLE_ID\)/);
  assert.equal(/htmlFor = INPUT_ID/.test(src), false, "підпис поля тепер — заголовок, не <label>");
});

test("tellError — повідомлення з класом помилки й іконкою зі спрайта, без імпорту icons.js", () => {
  assert.equal(typeof tellError, "function");
  assert.match(src, /export const tellError = \(title, reason\) =>/);
  assert.match(src, /cv-ask--error/);
  assert.match(src, /'#i-warn'/);
});

test("поповер: без підкладки, клас cv-ask-pop, закриття повз/якорем — але не під час busy", () => {
  assert.match(src, /'cv-ask-pop'/);
  assert.match(src, /popPlace\(/);
  assert.match(src, /if \(busy \|\| formEl\?\.getAttribute\('aria-busy'\) === 'true'\) return;/);
  assert.match(src, /addEventListener\('pointerdown', onOutside, true\)/);
  assert.match(src, /removeEventListener\('pointerdown', onOutside, true\)/);
  assert.match(src, /removeEventListener\('blur', onBlur\)/);
  assert.match(src, /removeEventListener\('resize', place\)/);
});

import { setLang, t } from "../app/i18n.js";

const ERR_TITLES = ["errTDupIter", "errTOpenTask", "errTSpaceSwitch", "errTRenameIter", "errTDeleteIter", "errTVcsPush",
  "errTVcsPull", "errTPublish", "errTTeamsMute", "errTPreviewPw", "errTRenamePage", "errTMovePage", "errTPagePublish"];

test("заголовки помилок дій — є в обох мовах і починаються з «Не вдалося» / «Could not»", () => {
  for (const lang of ["uk", "en"]) {
    setLang(lang);
    for (const k of ERR_TITLES) assert.match(t(k), lang === "uk" ? /^Не вдалося / : /^Could not /, `${lang}:${k}`);
  }
  setLang("uk");
});

test("кожен живий tell(t('errFailed', …)) у app.js замінено на tellError, крім мертвого pillMenu", () => {
  const app = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");
  const start = app.indexOf("function pillMenu(");
  const end = app.indexOf("\n}\n", start);
  const live = app.slice(0, start) + app.slice(end);
  assert.equal((live.match(/tell\(t\('errFailed'/g) || []).length, 0);
  assert.equal((live.match(/tellError\(t\('errT/g) || []).length, 13);
});

test("заголовок питання — короткий перший рядок", () => {
  setLang("uk");
  for (const [k, args] of [["menuDeletePageConfirm", []], ["delTreeTitle", ["Картка", 3]], ["inspTunerResetAllAsk", [2]]]) {
    const first = t(k, ...args).split("\n")[0];
    assert.ok(first.length <= 80 && /\?$/.test(first), `${k}: «${first}»`);
  }
});

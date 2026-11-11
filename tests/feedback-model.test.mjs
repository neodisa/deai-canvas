/**
 * Відгук (0.23.0), інтерфейс: модель (`app/feedback-model.js`), розмітка (`app/feedback-view.js`), проводка в `app.js` (текст-виборка;
 * живий прогін — T10). Головні охоронці: екранування всього, що з сервера, і ТОЙ САМИЙ масив помилок клієнта в перегляді й відправці.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { DICT, setLang, t } from "../app/i18n.js";
import {
  CONTACT_MAX, TEXT_MAX, TEXT_MIN, createSession, errArg, errField, outcome, previewText, sentView, serverErrKey, shotState, validate,
} from "../app/feedback-model.js";
import { feedbackBtnHTML, feedbackDialogHTML } from "../app/feedback-view.js";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app");
const appJs = readFileSync(path.join(APP, "app.js"), "utf8");

test.beforeEach(() => setLang("uk"));

const OK10 = "x".repeat(TEXT_MIN);

/* ── перевірка форми ─────────────────────────────────────────────────────── */

test("validate: межі тексту (по trim), контакту й типу", () => {
  assert.equal(validate({ kind: "bug", text: OK10 }), null);
  assert.equal(validate({ kind: "bug", text: "x".repeat(TEXT_MIN - 1) }), "fbErrShort");
  assert.equal(validate({ kind: "bug", text: `   ${"x".repeat(TEXT_MIN - 1)}   ` }), "fbErrShort", "пробіли не рахуються");
  assert.equal(validate({ kind: "idea", text: "x".repeat(TEXT_MAX) }), null);
  assert.equal(validate({ kind: "idea", text: "x".repeat(TEXT_MAX + 1) }), "fbErrLong");
  assert.equal(validate({ kind: "bug", text: OK10, contact: "c".repeat(CONTACT_MAX) }), null);
  assert.equal(validate({ kind: "bug", text: OK10, contact: "c".repeat(CONTACT_MAX + 1) }), "fbErrContact");
  for (const kind of [undefined, "", "BUG", "feature"]) assert.equal(validate({ kind, text: OK10 }), "fbErrKind");
  assert.equal(validate(), "fbErrKind");
  assert.equal(validate({ kind: "bug", text: "😀".repeat(TEXT_MIN) }), null, "довжина — у символах, не в одиницях UTF-16");
});

test("помилки: поле, аргумент межі й відповідність кодам сервера; усі ключі є в обох словниках", () => {
  assert.equal(errField("fbErrShort"), "text");
  assert.equal(errField("fbErrLong"), "text");
  assert.equal(errField("fbErrContact"), "contact");
  assert.equal(errField("fbErrKind"), "kind");
  assert.equal(errArg("fbErrShort"), TEXT_MIN);
  assert.equal(errArg("fbErrLong"), TEXT_MAX);
  assert.equal(errArg("fbErrContact"), CONTACT_MAX);
  assert.equal(serverErrKey("bad-kind"), "fbErrKind");
  assert.equal(serverErrKey("text-too-short"), "fbErrShort");
  assert.equal(serverErrKey("text-too-long"), "fbErrLong");
  assert.equal(serverErrKey("bad-contact"), "fbErrContact");
  assert.equal(serverErrKey("contact-too-long"), "fbErrContact");
  assert.equal(serverErrKey("bad-flag"), null);
  for (const lang of ["uk", "en"]) {
    setLang(lang);
    for (const k of ["fbErrShort", "fbErrLong", "fbErrContact"]) assert.match(t(k, 10), /10/);
  }
});

/* ── тіла запитів ────────────────────────────────────────────────────────── */

const CTX = { task: "T-1", it: "it2", node: "main", screen: "single" };
const form = (o = {}) => ({ kind: "bug", text: `  ${OK10}  `, contact: "  a@example.com ", includeDiag: true, includeShot: false, shotAvailable: false, ...o });

test("sendBody: поля, trim, include_shot лише коли кадр є й галочка стоїть", () => {
  const s = createSession({ ctx: CTX, clientErrors: [{ msg: "e", file: "", line: 0 }], lang: "uk" });
  assert.deepEqual(s.sendBody(form()), {
    kind: "bug", text: OK10, contact: "a@example.com", task: "T-1", it: "it2", node: "main", screen: "single", lang: "uk",
    client_errors: [{ msg: "e", file: "", line: 0 }], include_diag: true, include_shot: false,
  });
  assert.equal(s.sendBody(form({ includeShot: true, shotAvailable: false })).include_shot, false, "галочка без кадру не шле знімок");
  assert.equal(s.sendBody(form({ includeShot: true, shotAvailable: true })).include_shot, true);
  assert.equal(s.sendBody(form({ includeShot: false, shotAvailable: true })).include_shot, false);
  assert.equal(s.sendBody(form({ includeDiag: false })).include_diag, false);
  assert.equal("contact" in s.sendBody(form({ contact: "   " })), false, "порожній контакт не шлеться");
});

test("сесія без контексту: порожні task/it/node/screen не потрапляють у тіло", () => {
  const b = createSession({ ctx: { task: "", screen: "tasks" }, clientErrors: [], lang: "en" }).previewBody();
  assert.deepEqual(b, { screen: "tasks", lang: "en", client_errors: [] });
});

test("перегляд і відправка читають ТОЙ САМИЙ масив помилок клієнта (знімок при створенні сесії)", () => {
  const ring = [{ msg: "a", file: "app/app.js", line: 1 }];
  const s = createSession({ ctx: CTX, clientErrors: ring, lang: "uk" });
  assert.strictEqual(s.previewBody().client_errors, s.sendBody(form()).client_errors, "різні масиви: людина бачила одне, а піде інше");
  assert.strictEqual(s.previewBody().client_errors, s.clientErrors);
  assert.strictEqual(s.previewBody().client_errors, s.previewBody().client_errors);
});

/* ── результат ───────────────────────────────────────────────────────────── */

test("outcome: sent / queued (no-collector, інші) / memory_only; тексти обох мов", () => {
  assert.deepEqual(outcome({ state: "sent", number: "ab12" }), { key: "fbSent", args: ["ab12"], suffixKey: null });
  assert.equal(outcome({ state: "queued", reason: "no-collector", number: "n" }).key, "fbQueuedNoCollector");
  for (const reason of ["offline", "rejected", "network-blocked", "other", undefined]) {
    assert.equal(outcome({ state: "queued", reason, number: "n" }).key, "fbQueued", String(reason));
  }
  assert.equal(outcome({ state: "queued", reason: "offline", number: "n", memory_only: true }).suffixKey, "fbMemOnly");
  assert.equal(outcome({ state: "sent", number: "n", memory_only: true }).suffixKey, null, "надіслане не «лише до перезапуску»");
  assert.equal(t("fbSent", "ab12"), "Дякуємо! Відгук №ab12 надіслано");
  assert.equal(t("fbQueuedNoCollector", "ab12"), "Збережено локально (№ab12) — надішлемо, щойно приймач буде налаштовано");
  assert.equal(t("fbQueued", "ab12"), "Збережено локально (№ab12), надішлемо пізніше");
  assert.equal(t("fbMemOnly"), "(лише до перезапуску)");
  setLang("en");
  assert.match(t("fbSent", "ab12"), /ab12/);
  assert.match(t("fbQueuedNoCollector", "ab12"), /collector/);
  assert.equal(outcome(null).key, "fbQueued");
});

test("shotState і sentView: що піде при цих галочках", () => {
  assert.deepEqual(shotState({ shot: { available: true, bytes: 900 } }), { available: true, bytes: 900, reasonKey: null });
  assert.equal(shotState({ shot: { available: false } }).reasonKey, "fbShotNone");
  assert.equal(shotState({ shot: { available: false, bytes: 3000000, skipped: "too-big" } }).reasonKey, "fbShotTooBig");
  assert.equal(shotState(null).available, false);
  const p = { diag: { version: "0.23.0" }, shot: { available: true, bytes: 10 } };
  assert.deepEqual(sentView(p, { includeDiag: true, includeShot: true }), { diag: { version: "0.23.0" }, shot: { attached: true, bytes: 10 } });
  assert.deepEqual(sentView(p, { includeDiag: false, includeShot: false }), { diag: {}, shot: { attached: false } });
  assert.equal(sentView({ ...p, shot: { available: false } }, { includeDiag: true, includeShot: true }).shot.attached, false);
});

test("previewText: стабільний відступний JSON, ключі за абеткою", () => {
  assert.equal(previewText({ b: 1, a: { d: 1, c: 2 } }), '{\n  "a": {\n    "c": 2,\n    "d": 1\n  },\n  "b": 1\n}');
});

/* ── розмітка ────────────────────────────────────────────────────────────── */

const XSS = "<img src=x onerror=alert(1)>";
const DIAG = { version: "0.23.0", errors: { server: [{ route: "/api/x", type: "ValueError", msg: XSS }], client: [{ msg: XSS, file: "app/app.js", line: 1 }] } };

test("діалог: контракт askForm (форма, радіо, текстове поле, чекбокси, details/pre, слот помилки, кнопки)", () => {
  const h = feedbackDialogHTML({ shot: { available: false, reasonKey: "fbShotNone" }, previewText: previewText({ diag: {} }) });
  assert.match(h, /<form[^>]*data-form="feedback"[^>]*role="dialog"[^>]*aria-modal="true"/);
  assert.match(h, /<input type="radio" name="kind" value="bug" checked>/);
  assert.match(h, /<input type="radio" name="kind" value="idea">/);
  assert.match(h, /<textarea id="fb-text" name="text"[^>]*required[^>]*aria-describedby="cv-form-err"/);
  assert.match(h, /<input id="fb-contact" name="contact"/);
  assert.match(h, /<input type="checkbox" id="fb-diag" name="diag" checked>/);
  assert.match(h, /<input type="checkbox" id="fb-shot" name="shot" disabled aria-describedby="fb-shot-why">/);
  assert.match(h, /id="fb-shot-why">Знімка поточної сторінки немає/, "причина вимкненого чекбокса видима");
  assert.match(h, /<details[^>]*data-fb-preview[^>]*>[\s\S]*<pre[^>]*data-fb-pre/);
  assert.match(h, /id="cv-form-err"[^>]*data-form-error[^>]*hidden/);
  assert.match(h, /data-a="cancel"/);
  assert.match(h, /type="submit" data-a="ok"/);
  const on = feedbackDialogHTML({ shot: { available: true, bytes: 5 }, previewText: "{}", includeShot: true });
  assert.match(on, /id="fb-shot" name="shot" checked>/);
  assert.doesNotMatch(on, /fb-shot-why/);
});

test("діалог: усе з даних (діагностика, текст, контакт) — лише екрановане", () => {
  const h = feedbackDialogHTML({
    kind: "idea", text: `</textarea>${XSS}`, contact: `"><script>x</script>`, shot: { available: false, reasonKey: "fbShotNone" },
    previewText: previewText({ diag: DIAG }),
  });
  assert.ok(!h.includes(XSS), "сирий <img> потрапив у розмітку");
  assert.ok(!h.includes("<script>"), "сирий <script> потрапив у розмітку");
  assert.ok(!h.includes("</textarea><img"), "текст розірвав textarea");
  assert.ok(h.includes("&lt;img src=x onerror=alert(1)&gt;"));
  assert.match(h, /<input type="radio" name="kind" value="idea" checked>/);
  assert.ok(h.split("\n").some((l) => l.includes('<pre') && !l.includes("<img")), "pre без сирої розмітки");
});

test("діалог без перегляду: у pre — фраза, що перегляд недоступний", () => {
  const h = feedbackDialogHTML({ shot: { available: false, reasonKey: "fbShotNone" }, previewText: "" });
  assert.ok(h.includes("Нічого, крім вашого тексту.") || h.includes(t("fbPreviewNone")));
});

test("кнопка в смузі: іконка, title/aria-label зі словника, без підпису в тексті", () => {
  const h = feedbackBtnHTML({ id: "feedback" });
  assert.match(h, /data-act="feedback"/);
  assert.match(h, /title="Баг \/ ідея" aria-label="Баг \/ ідея"/);
  assert.match(h, /class="ctl ctl--icon fb-btn"/);
  assert.equal(feedbackBtnHTML(undefined), "");
});

/* ── проводка app.js (текст-виборка) ─────────────────────────────────────── */

test("app.js: дії feedback в BAR_ACTIONS, діалог на askForm, помилки кільця й відповідей — через textContent/ctl.error", () => {
  assert.match(appJs, /^\s*feedback: \(\) => openFeedback\(\),/m);
  assert.match(appJs, /askForm\(\(\) => feedbackDialogHTML\(/);
  assert.match(appJs, /jsonPost\('\/api\/feedback-preview', sess\.previewBody\(\)\)/);
  assert.match(appJs, /jsonPost\('\/api\/feedback', sess\.sendBody\(/);
  assert.match(appJs, /pre\.textContent = shownText\(/, "оновлення «Що буде надіслано» — лише textContent");
  const fb = appJs.slice(appJs.indexOf("async function openFeedback"));
  assert.doesNotMatch(fb.slice(0, fb.indexOf("feedbackDialogOpen = false")), /innerHTML/);
});

test("усі ключі fb* є в обох словниках", () => {
  const uk = Object.keys(DICT.uk).filter((k) => k.startsWith("fb")).sort();
  const en = Object.keys(DICT.en).filter((k) => k.startsWith("fb")).sort();
  assert.deepEqual(uk, en);
  assert.ok(uk.length >= 25);
});

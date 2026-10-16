import assert from "node:assert/strict";
import test from "node:test";

import { DICT } from "../app/i18n.js";
import {
  copyUrl, hasPublish, isLegacyPublish, isPublished, localPublishUrl, previewTarget, publishErr, pwView,
  safeLocalUrl,
} from "../app/spaces-model.js";

/* Публікація за `capabilities.publish` (модулі 2а, Task 8) — чисті правила, які приймає `app.js`:
   хто публікує простір, чи задача опублікована, куди веде «Відкрити превью»/«Скопіювати
   посилання», що з паролем ЛІГА в просторі, де публікує модуль, і який текст людина бачить
   замість коду відмови. `app.js` у Node не імпортується (DOM на верхньому рівні), тому проводку
   стереже `tests/spaces-wiring.test.mjs`, а тут — самі правила.

   `capabilities` приходить від сервера ТОТАЛЬНО: `{publish: '<id модуля>' | 'legacy' | null,
   tokens: …[, error]}`. Стара форма відповіді (без `capabilities`) лишається валідною: тоді
   рішення — за `integrations`, як було до модулів. */

const MOD = { id: "p", integrations: false, capabilities: { publish: "static-publish", tokens: null } };
const LEG = { id: "liga", integrations: true, capabilities: { publish: "legacy", tokens: null } };
const NONE = { id: "n", integrations: false, capabilities: { publish: null, tokens: null } };

/* ── хто публікує ──────────────────────────────────────────────────────── */

test("hasPublish: модуль — так, legacy — так, null — ні", () => {
  assert.equal(hasPublish(MOD), true);
  assert.equal(hasPublish(LEG), true);
  assert.equal(hasPublish(NONE), false);
});

test("hasPublish: стара форма (без capabilities) — за `integrations`, невідомість публікації не краде", () => {
  assert.equal(hasPublish({ integrations: false }), false, "старий простір без інтеграцій: публікації нема");
  assert.equal(hasPublish({ integrations: true }), true);
  assert.equal(hasPublish({}), true, "відповідь без відомостей не краде публікацію");
  assert.equal(hasPublish(null), true);
  assert.equal(hasPublish(undefined), true);
});

test("hasPublish: capabilities ВАЖЧІ за integrations (простір без інтеграцій може публікувати модулем)", () => {
  assert.equal(hasPublish({ integrations: false, capabilities: { publish: "static-publish" } }), true);
  assert.equal(hasPublish({ integrations: true, capabilities: { publish: null } }), false,
    "модуль публікації вимкнено — публікації нема, хоч би інтеграції й були");
});

test("hasPublish: capabilities із помилкою (space.json не читається) — публікації нема", () => {
  assert.equal(hasPublish({ integrations: false, capabilities: { publish: null, tokens: null, error: "space-json-unreadable" } }), false);
});

test("isLegacyPublish: лише 'legacy' (або стара форма з інтеграціями)", () => {
  assert.equal(isLegacyPublish(LEG), true);
  assert.equal(isLegacyPublish(MOD), false);
  assert.equal(isLegacyPublish(NONE), false);
  assert.equal(isLegacyPublish({ integrations: true }), true);
  assert.equal(isLegacyPublish({ integrations: false }), false);
  assert.equal(isLegacyPublish({}), true);
  assert.equal(isLegacyPublish(null), true);
  assert.equal(isLegacyPublish({ integrations: true, capabilities: { publish: "static-publish" } }), false,
    "модуль замість ЛІГА: пароль превʼю ЛІГА там нічого не значить");
});

/* ── чи опублікована задача ────────────────────────────────────────────── */

test("isPublished: publish_url АБО publish_local", () => {
  assert.equal(isPublished({ publish_url: "https://x.example/" }), true);
  assert.equal(isPublished({ publish_local: { module: "static-publish", path: "/a/b", published_at: "2026-10-16T10:00:00Z" } }), true);
  assert.equal(isPublished({}), false);
  assert.equal(isPublished({ publish_url: null }), false);
  assert.equal(isPublished({ publish_url: "" }), false);
  assert.equal(isPublished(null), false);
  assert.equal(isPublished({ publish_local: null }), false);
  assert.equal(isPublished({ publish_local: "рядок" }), false, "publish_local — обʼєкт, не будь-яка правда");
});

/* ── адреса локальної публікації ───────────────────────────────────────── */

test("localPublishUrl: /published/<простір>/<задача>/, кожен сегмент через encodeURIComponent", () => {
  assert.equal(localPublishUrl({ id: "p" }, { id: "blog" }), "/published/p/blog/");
  assert.equal(localPublishUrl({ id: "a b/c" }, { id: "t#1?x" }), "/published/a%20b%2Fc/t%231%3Fx/");
});

test("localPublishUrl: без id простору чи задачі — null (адреси не вигадуємо)", () => {
  assert.equal(localPublishUrl(null, { id: "t" }), null);
  assert.equal(localPublishUrl({ id: "" }, { id: "t" }), null);
  assert.equal(localPublishUrl({ id: "p" }, {}), null);
  assert.equal(localPublishUrl({ id: "p" }, null), null);
});

const LOCAL = { module: "static-publish", path: "/h/deai-published/p/blog", published_at: "2026-10-16T10:30:00Z" };

test("previewTarget: простір з модулем — локальна адреса канваса і час публікації", () => {
  const tg = previewTarget({ id: "blog", publish_local: LOCAL }, MOD);
  assert.equal(tg.kind, "local");
  assert.equal(tg.url, "/published/p/blog/");
  assert.equal(tg.at, Date.parse("2026-10-16T10:30:00Z"));
});

test("previewTarget: ЛІГА — зовнішній URL, час не вигадуємо", () => {
  const tg = previewTarget({ id: "blog", publish_url: "https://pv-1.example.app" }, LEG);
  assert.deepEqual(tg, { kind: "external", url: "https://pv-1.example.app", at: null });
});

test("previewTarget: обидва сліди — перемагає той, що відповідає постачальнику простору", () => {
  const task = { id: "blog", publish_url: "https://pv-1.example.app", publish_local: LOCAL };
  assert.equal(previewTarget(task, MOD).kind, "local");
  assert.equal(previewTarget(task, LEG).kind, "external");
});

test("previewTarget: простір із модулем, де є лише старий publish_url, — відкриваємо його (слід не губимо)", () => {
  assert.equal(previewTarget({ id: "blog", publish_url: "https://pv-1.example.app" }, MOD).kind, "external");
});

test("previewTarget: нічого не публікувалось — null; локальна без id простору — null", () => {
  assert.equal(previewTarget({ id: "blog" }, MOD), null);
  assert.equal(previewTarget(null, MOD), null);
  assert.equal(previewTarget({ id: "blog", publish_local: LOCAL }, null), null, "адреси без простору не буде");
});

test("previewTarget: непридатний час публікації — at: null, а не NaN", () => {
  assert.equal(previewTarget({ id: "blog", publish_local: { ...LOCAL, published_at: "вчора" } }, MOD).at, null);
  assert.equal(previewTarget({ id: "blog", publish_local: { module: "static-publish", path: "/x" } }, MOD).at, null);
});

/* ── посилання, яке копіюють ───────────────────────────────────────────── */

test("copyUrl: локальна — абсолютна адреса канваса БЕЗ #k= (пароль модуля — секрет, UI його не знає)", () => {
  const tg = { kind: "local", url: "/published/p/blog/", at: null };
  const url = copyUrl(tg, { origin: "http://localhost:8765", pageId: "it1/home", password: "1100" });
  assert.equal(url, "http://localhost:8765/published/p/blog/");
  assert.ok(!url.includes("#"), "у локальному посиланні нема фрагмента");
  assert.ok(!url.includes("k="), "пароль не в посиланні");
  assert.ok(!url.includes("1100"), "ЛІГА-пароль не просочується в локальне посилання");
});

test("copyUrl: зовнішня — як було: <url>/#k=<пароль>&p=<сторінка>, обидва закодовані", () => {
  const tg = { kind: "external", url: "https://pv-1.example.app///", at: null };
  assert.equal(copyUrl(tg, { pageId: "it4/page 2", password: "p&w" }),
    "https://pv-1.example.app/#k=p%26w&p=it4%2Fpage%202");
  assert.equal(copyUrl(tg, { pageId: "it4" }), "https://pv-1.example.app/#k=&p=it4");
});

test("copyUrl: без цілі — null", () => {
  assert.equal(copyUrl(null, { origin: "http://x" }), null);
});

/* ── довіряти відповіді сервера, куди відкривати ───────────────────────── */

const ORIGIN = "http://127.0.0.1:8765";

test("safeLocalUrl: лише відносний шлях /published/…", () => {
  assert.equal(safeLocalUrl("/published/p/blog/", ORIGIN), "/published/p/blog/");
  assert.equal(safeLocalUrl("/published/a%20b/t/", ORIGIN), "/published/a%20b/t/");
  assert.equal(safeLocalUrl("/published/p/blog/?x=1#y", ORIGIN), "/published/p/blog/?x=1#y");
  for (const bad of ["https://evil.example/", "//evil.example/published/", "/other/p/t/", "published/p/t/", "",
    null, undefined, 42, "/published/", "/published/\\evil", "/published/p t/", "javascript:alert(1)"]) {
    assert.equal(safeLocalUrl(bad, ORIGIN), null, String(bad));
  }
});

test("safeLocalUrl: крапкові складові не виводять з /published/ (`..`, `%2e%2e` у будь-якому регістрі)", () => {
  /* Браузер зводить ці адреси в `/api/task` — вони ПОВИННІ відкидатись, хоч на вигляд і під /published/. */
  assert.equal(new URL("/published/../api/task", ORIGIN).pathname, "/api/task", "свідок: браузер справді зводить `..`");
  assert.equal(new URL("/published/%2e%2e/api/task", ORIGIN).pathname, "/api/task", "свідок: і `%2e%2e`");
  for (const bad of ["/published/../api/task", "/published/%2e%2e/api/task", "/published/%2E%2E/api/task",
    "/published/%2e./api/task", "/published/.%2E/api/task", "/published/./p/", "/published/p/./t/", "/published/p/../t/",
    "/published/p/..%2f..%2fapi/task", "/published/p/%2e%2e%2fapi/task", "/published/p%5c..%5capi/task",
    "/published/%2e/p/", "/published/p/t/..?x", "/published/p/t/%2e%2e#x", "/published/%zz/"]) {
    assert.equal(safeLocalUrl(bad, ORIGIN), null, bad);
  }
});

test("safeLocalUrl: розвʼязана адреса лишається на оригіні канваса й під /published/", () => {
  // Нормальні id з крапкою всередині складової — не крапкова складова.
  assert.equal(safeLocalUrl("/published/p/blog.v2/", ORIGIN), "/published/p/blog.v2/");
  assert.equal(safeLocalUrl("/published/p/..blog/", ORIGIN), "/published/p/..blog/");
  // Недійсний оригін — не вгадуємо, а відмовляємо.
  assert.equal(safeLocalUrl("/published/p/blog/", "не оригін"), null);
});

/* ── пароль превʼю ─────────────────────────────────────────────────────── */

const GATE_TASK = (state, extra = {}) => ({
  id: "blog", publish_url: "https://pv-1.example.app", preview_password: "1100", preview_password_custom: true,
  preview_gate: { state, stale: 2, ungated: 3, inner_stale: 0, pages: 5 }, ...extra,
});

test("pwView: ЛІГА — як було (пароль, свій/типовий, stale, ungated)", () => {
  assert.deepEqual(pwView(GATE_TASK("stale"), LEG), { pw: "1100", pwCustom: true, pwStale: true, pwUngated: 0 });
  assert.deepEqual(pwView(GATE_TASK("ungated"), LEG), { pw: "1100", pwCustom: true, pwStale: false, pwUngated: 3 });
  assert.deepEqual(pwView(GATE_TASK("current"), LEG), { pw: "1100", pwCustom: true, pwStale: false, pwUngated: 0 });
});

test("pwView: stale/ungated лише для ОПУБЛІКОВАНОЇ в ЛІГА задачі (нема publish_url — нема тривоги)", () => {
  const t = GATE_TASK("stale", { publish_url: null });
  assert.equal(pwView(t, LEG).pwStale, false);
  assert.equal(pwView(GATE_TASK("ungated", { publish_url: null }), LEG).pwUngated, 0);
});

test("pwView: простір, де публікує модуль, — жодних попереджень про пароль і жодного пароля ЛІГА", () => {
  // `preview_password` у відповіді сервера лишається ЛІГА-шним навіть тут: показувати його — брехня.
  const t = GATE_TASK("module");
  assert.deepEqual(pwView(t, MOD), { pw: "", pwCustom: false, pwStale: false, pwUngated: 0 });
  // і коли лічильники виставлено, а стан — 'module', попереджень однаково нема
  assert.equal(pwView({ ...t, preview_gate: { state: "module", stale: 9, ungated: 9 } }, MOD).pwStale, false);
  assert.equal(pwView({ ...t, preview_gate: { state: "module", stale: 9, ungated: 9 } }, MOD).pwUngated, 0);
  // навіть якщо сервер раптом дасть 'stale', модульний простір пароля ЛІГА не показує
  assert.equal(pwView(GATE_TASK("stale"), MOD).pw, "");
  assert.equal(pwView(GATE_TASK("stale"), MOD).pwStale, false);
});

test("pwView: стан 'module' від сервера — не 'stale' і не 'ungated' навіть для legacy-подібного простору", () => {
  const v = pwView(GATE_TASK("module"), LEG);
  assert.equal(v.pwStale, false);
  assert.equal(v.pwUngated, 0);
});

test("pwView: немає задачі — порожньо", () => {
  assert.deepEqual(pwView(null, LEG), { pw: "", pwCustom: false, pwStale: false, pwUngated: 0 });
});

/* ── помилки публікації → людський текст ───────────────────────────────── */

const E = (code, extra = {}) => Object.assign(new Error(extra.message ?? "сире повідомлення сервера"), { code, ...extra });

test("publishErr: коди модульної публікації → окремі ключі словника", () => {
  assert.equal(publishErr(E("no-publish-module", { status: 409 })).key, "publishErrNoModule");
  assert.equal(publishErr(E("publish-busy", { status: 409 })).key, "publishErrBusy");
  assert.equal(publishErr(E("bad-task-id", { status: 400 })).key, "publishErrBadTaskId");
  assert.equal(publishErr(E("module-error", { status: 502 })).key, "publishErrModule");
  assert.equal(publishErr(E("bad-folder", { status: 409, message: "path-too-broad" })).key, "publishErrBadFolder");
});

test("publishErr: bad-folder — людська причина зі словника просторів (`spaceErrKey`), а не сирий код", () => {
  const r = publishErr(E("bad-folder", { message: "path-too-broad" }));
  assert.equal(r.reasonKey, "spaceErrTooBroad");
  assert.deepEqual(r.args, [], "сирий код не їде поряд із людською причиною");
  for (const [code, key] of [["path-not-absolute", "spaceErrNotAbsolute"], ["path-system", "spaceErrSystem"],
    ["path-tool", "spaceErrTool"], ["path-registered", "spaceErrRegistered"], ["path-overlap", "spaceErrOverlap"],
    ["path-not-dir", "spaceErrNotDir"], ["path-unwritable", "spaceErrUnwritable"]]) {
    assert.equal(publishErr(E("bad-folder", { message: code })).reasonKey, key, code);
    assert.ok(DICT.uk[key] !== undefined && DICT.en[key] !== undefined, key);
  }
});

test("publishErr: bad-folder із кодом, якого словник просторів не знає, — сам код як запасний варіант", () => {
  for (const code of ["path-deai-home", "path-invalid", "spaces-unreadable"]) {
    assert.deepEqual(publishErr(E("bad-folder", { message: code })), { key: "publishErrBadFolder", args: [code] }, code);
  }
});

test("publishErr: bad-folder показує лише код path-*/spaces-*, а не будь-який текст сервера (і не `spaceErrGeneric`)", () => {
  for (const raw of ["/Users/ivan/Documents/секрет", "C:\\Users\\ivan", "path-x/../../etc", "path-", "", "щось ще",
    "path-too-broad і шлях /Users/ivan", "task-id-collision", "timeout", "name-required"]) {
    const r = publishErr(E("bad-folder", { message: raw }));
    assert.deepEqual(r, { key: "publishErrBadFolder", args: [""] }, `«${raw}» не мусить потрапити в текст`);
  }
});

test("publishErr: module-error не несе тексту модуля (там можуть бути шляхи)", () => {
  const r = publishErr(E("module-error", { status: 502, message: "boom at /Users/ivan/deai-published/p/blog" }));
  assert.deepEqual(r.args, []);
});

test("publishErr: 400 без коду з текстом «no iterations marked» (рядок статусу чи тіло) — окремий текст", () => {
  const real = "no iterations marked for publish - toggle the green dot first";
  for (const extra of [
    { statusText: real, message: "<!DOCTYPE HTML><html lang=\"en\"><head>…" },          // як у браузері: причина в рядку статусу
    { statusText: "", body: `<html><body><p>Message: ${real}.</p></body></html>`, message: "<!DOCTYPE HTML>" },
    { message: real },
  ]) {
    const r = publishErr(E(undefined, { status: 400, ...extra }));
    assert.equal(r.key, "publishErrNoIterations", JSON.stringify(extra));
    assert.deepEqual(r.args, []);
  }
});

test("publishErr: інший 400 без коду (`bad payload`) і 400 без тексту — загальна відмова, а не «нема ітерацій»", () => {
  for (const extra of [
    { statusText: "bad payload", message: "<!DOCTYPE HTML>…" },
    { statusText: "", body: "<p>Message: bad payload.</p>", message: "<!DOCTYPE HTML>…" },
    { message: "щось" },
  ]) {
    const r = publishErr(E(undefined, { status: 400, ...extra }));
    assert.equal(r.key, "errFailed", JSON.stringify(extra));
    assert.deepEqual(r.args, [extra.message]);
  }
});

test("publishErr: текст «no iterations marked» без статусу 400 чи з кодом — не підміняється", () => {
  assert.equal(publishErr(E(undefined, { status: 500, statusText: "no iterations marked" })).key, "errFailed");
  assert.equal(publishErr(E("bad-settings", { status: 400, statusText: "no iterations marked" })).key, "errFailed");
});

test("publishErr: решта — загальне «Не вдалося: …» із текстом сервера", () => {
  for (const [code, status] of [["secrets-unreadable", 409], ["space-json-unreadable", 409], ["bad-settings", 400],
    ["no-task", 404], ["constructor", 500], [undefined, 500], [undefined, undefined]]) {
    const r = publishErr(E(code, { status, message: "причина" }));
    assert.equal(r.key, "errFailed", `${code}/${status}`);
    assert.deepEqual(r.args, ["причина"]);
  }
  assert.equal(publishErr(null).key, "errFailed");
});

test("publishErr: кожен ключ є у словнику ОБОХ мов", () => {
  const keys = new Set();
  for (const e of [E("no-publish-module"), E("publish-busy"), E("bad-task-id"), E("module-error"),
    E("bad-folder", { message: "path-too-broad" }), E("bad-folder", { message: "path-invalid" }),
    E(undefined, { status: 400, statusText: "no iterations marked for publish" }), E("other")]) {
    const r = publishErr(e);
    keys.add(r.key);
    if (r.reasonKey) keys.add(r.reasonKey);
  }
  for (const k of keys) {
    assert.ok(DICT.uk[k] !== undefined && DICT.en[k] !== undefined, `«${k}» бракує в словнику`);
  }
});

test("словник: підписи локальної публікації — обидві мови, без сирого ISO", () => {
  for (const k of ["publishLocalDone", "publishOpen", "publishLocalSub", "publishLocalLinkSub",
    "publishErrNoModule", "publishErrBadFolder", "publishErrBusy", "publishErrBadTaskId", "publishErrModule",
    "publishErrNoIterations"]) {
    assert.ok(DICT.uk[k] !== undefined && DICT.en[k] !== undefined, `«${k}» бракує в словнику`);
  }
  assert.match(DICT.uk.publishLocalSub("5 хв тому"), /локально/);
  assert.match(DICT.uk.publishLocalSub("5 хв тому"), /5 хв тому/);
  assert.match(DICT.en.publishLocalSub("5 min ago"), /local/);
  assert.equal(DICT.uk.publishLocalSub(""), "локально", "без часу — лише позначка, без висячого «·»");
  assert.equal(DICT.en.publishLocalSub(""), "local");
  assert.match(DICT.uk.publishErrBadFolder("ТЕКСТ-ПРИЧИНИ"), /ТЕКСТ-ПРИЧИНИ/);
  assert.match(DICT.en.publishErrBadFolder("REASON-TEXT"), /REASON-TEXT/);
  assert.doesNotMatch(DICT.uk.publishErrBadFolder(""), /\(\)|:\s*$/, "без причини — без порожніх дужок і висячого двокрапка");
  assert.doesNotMatch(DICT.en.publishErrBadFolder(""), /\(\)|:\s*$/);
});

/* Тексти не обіцяють того, чого в 2а нема: керування модулями в UI — етап 3 (у 2а лише API), а публікація
   у просторі без інтеграцій ПРАЦЮЄ (у локальну теку) — і «зʼявиться з модулями» про неї вже неправда. */
test("словник: ні публікація «зʼявиться з модулями», ні «налаштування простору» як дверей, яких нема", () => {
  for (const lang of ["uk", "en"]) {
    const d = DICT[lang];
    assert.doesNotMatch(d.integrationsOff, lang === "uk" ? /публікація, GitLab/ : /publishing, GitLab/, `${lang}: integrationsOff`);
    assert.match(d.integrationsOff, lang === "uk" ? /публікація йде в локальну теку/ : /publishing goes to a local folder/);
    assert.match(d.integrationsOff, /GitLab/);
    for (const k of ["publishErrNoModule", "publishErrBadFolder"]) {
      const text = typeof d[k] === "function" ? d[k]("") : d[k];
      assert.doesNotMatch(text, /налаштуваннях простору|space settings|You can turn/i, `${lang}: ${k} обіцяє UI налаштувань`);
    }
  }
  assert.match(DICT.uk.publishErrNoModule, /вимкнено для цього простору/);
  assert.match(DICT.en.publishErrNoModule, /turned off for this space/);
});

test("словник: publishErrBadTaskId називає зарезервовані імена Windows (обидві мови)", () => {
  for (const lang of ["uk", "en"]) {
    for (const name of ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"]) {
      assert.ok(DICT[lang].publishErrBadTaskId.includes(name), `${lang}: нема ${name}`);
    }
  }
});

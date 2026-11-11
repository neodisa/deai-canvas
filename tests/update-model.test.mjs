/**
 * Оновлення інструмента (0.23.0), інтерфейс: чиста модель (`app/update-model.js`) і розмітка (`app/update-view.js`).
 * Проводку `app.js` (опит після рестарту, діалог) тут стережемо текстом-виборкою: живий прогін — T10.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { DICT, setLang } from "../app/i18n.js";
import {
  KNOWN_CODES, NOTES_REASONS, RESTART_DEADLINE_MS, blockedHelp, bodyToBlocks, codeKey, codeOfBody, notesToBlocks, pillModel, restartStep,
} from "../app/update-model.js";
import { updateDialogHTML, updateNotesHTML, updatePillHTML } from "../app/update-view.js";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app");
const appJs = readFileSync(path.join(APP, "app.js"), "utf8");

const OK = { current: "0.1.0", latest: "0.2.0", available: true, state: "ok", checked_at: 1, blocked: null, boot: "a", restart_failed: false };

/* ── пігулка ─────────────────────────────────────────────────────────────── */

test("пігулка лише коли available і остання перевірка вдала; offline/error/disabled/no-git і «ще не питали» мовчать", () => {
  assert.deepEqual(pillModel(OK), { version: "0.2.0", labelKey: "upPill", restart: false });
  for (const state of ["offline", "error", "disabled", "no-git", null]) {
    assert.equal(pillModel({ ...OK, state }), null, `state=${state}`);
  }
  assert.equal(pillModel({ ...OK, available: false }), null, "оновлення нема");
  assert.equal(pillModel({ ...OK, latest: null }), null, "версії нема");
  assert.equal(pillModel({ current: "0.1.0", state: null, checked_at: null, available: false }), null, "до першої перевірки (state і checked_at = null)");
  for (const bad of [null, undefined, 5, "x"]) assert.equal(pillModel(bad), null);
});

test("пігулка: невдалий перезапуск після оновлення — окрема пігулка «потрібен перезапуск» (інакше діалогу ніде знайти)", () => {
  const m = pillModel({ ...OK, available: false, current: "0.2.0", restart_failed: true });
  assert.deepEqual(m, { version: "0.2.0", labelKey: "upPillRestart", restart: true });
});

/* ── довідка до кодів ────────────────────────────────────────────────────── */

/* Контракт сервера (`app/updater.py`), ПЕРЕПИСАНИЙ тут літералом: перелік, який тест бере з самого модуля, підтвердив би будь-який
   перелік — і пропущений код мовчав би. Новий код сервера — правка тут і в словнику одночасно. */
const CODES_B = ["not-git", "dirty", "detached", "worktree", "busy", "isolated", "diverged", "tag-conflict", "tag-missing", "tag-mismatch",
  "fetch-rejected", "offline", "disabled", "bad-remote", "no-remote", "rolled-back", "rollback-failed", "merge-failed", "nothing-to-update", "error"];
const REASONS_D = ["busy", "offline", "disabled", "no-update", "no-git", "fetch-rejected", "tag-missing", "tag-conflict", "no-changelog", "error",
  "bad-remote", "no-remote"];

test("перелік кодів і причин моделі збігається з контрактом сервера (B, D)", () => {
  assert.deepEqual([...KNOWN_CODES].sort(), [...CODES_B].sort());
  assert.deepEqual([...NOTES_REASONS].sort(), [...REASONS_D].sort());
  for (const code of CODES_B) assert.notEqual(codeKey(code), "upCode_generic", `${code}: невідомий моделі`);
});


test("blockedHelp: кожен код дає ключ, що є в обох словниках; команди — шаблони без шляхів; невідомий код → generic", () => {
  for (const code of CODES_B) {
    const h = blockedHelp(code, "0.2.0");
    assert.equal(h.key, `upCode_${code.replace(/-/g, "_")}`, code);
    for (const lang of ["uk", "en"]) assert.ok(DICT[lang][h.key] !== undefined, `${lang}.${h.key}`);
  }
  assert.equal(blockedHelp("dirty", "0.2.0").command, "git stash");
  assert.equal(blockedHelp("diverged", "0.2.0").command, "git merge v0.2.0");
  for (const code of CODES_B.filter((c) => c !== "dirty" && c !== "diverged")) {
    assert.equal(blockedHelp(code, "0.2.0").command, undefined, `${code}: команди не має бути`);
  }
  for (const h of CODES_B.map((c) => blockedHelp(c, "0.2.0")).filter((x) => x.command)) {
    assert.doesNotMatch(h.command, /[/\\~]/, "у команді немає шляхів");
  }
  const g = blockedHelp("something-new", "0.2.0");
  assert.equal(g.key, "upCode_generic");
  assert.equal(g.command, undefined);
  assert.equal(codeKey(undefined), "upCode_generic");
  assert.equal(blockedHelp("diverged", "0.2.0; rm -rf x").command, undefined, "сміття замість версії команди не дає");
  assert.equal(blockedHelp("diverged", null).command, undefined);
});

test("кожен код має текст в обох мовах — і функція generic приймає код", () => {
  for (const lang of ["uk", "en"]) {
    for (const code of CODES_B) assert.equal(typeof DICT[lang][codeKey(code)], "string", `${lang}:${code}`);
    assert.equal(typeof DICT[lang].upCode_generic, "function");
    assert.match(DICT[lang].upCode_generic("zzz"), /zzz/);
  }
});

test("codeOfBody: код із тіла; 403 лише з `error` і порожнє тіло — «error»", () => {
  assert.equal(codeOfBody({ ok: false, code: "dirty" }), "dirty");
  assert.equal(codeOfBody({ ok: false, error: "foreign origin" }), "error");
  assert.equal(codeOfBody(null), "error");
  assert.equal(codeOfBody({ code: 5 }), "error");
});

/* ── опит після рестарту ─────────────────────────────────────────────────── */

test("restartStep: чекаємо, поки boot змінився І current == target; помилка мережі = wait; дедлайн = fail", () => {
  const s = (o) => restartStep({ prevBoot: "a", target: "0.2.0", startedAt: 0, now: 1000 }, o);
  assert.equal(s({ ok: false }), "wait", "сервер ще лежить");
  assert.equal(s({ ok: true, boot: "a", current: "0.2.0" }), "wait", "старий процес уже бачить нову версію на диску (Поправка 9)");
  assert.equal(s({ ok: true, boot: "b", current: "0.1.0" }), "fail", "новий процес, але версія не та (відкат)");
  assert.equal(s({ ok: true, boot: "b", current: "0.2.0" }), "done");
  assert.equal(restartStep({ prevBoot: "a", target: "0.2.0", startedAt: 0, now: RESTART_DEADLINE_MS + 1 }, { ok: false }), "fail");
  assert.equal(restartStep({ prevBoot: "a", target: "0.2.0", startedAt: 0, now: RESTART_DEADLINE_MS + 1 }, { ok: true, boot: "a", current: "0.2.0" }), "fail",
    "старий процес до дедлайну — теж fail: рестарту не було");
  assert.equal(restartStep({ prevBoot: "a", target: "0.2.0", startedAt: 0, now: RESTART_DEADLINE_MS }, { ok: false }), "wait", "рівно на межі ще чекаємо");
});

test("restartStep: сервер сам визнав невдалий перезапуск (restart_failed у тому ж процесі) → manual", () => {
  const ctx = { prevBoot: "a", target: "0.2.0", startedAt: 0, now: 1000 };
  assert.equal(restartStep(ctx, { ok: true, boot: "a", current: "0.2.0", restart_failed: true }), "manual");
  assert.equal(restartStep(ctx, { ok: true, boot: "b", current: "0.2.0", restart_failed: true }), "done", "новий процес: прапорець застарів сам");
});

test("app.js: опит після рестарту йде через restartStep, з прапорцем boot з ПОПЕРЕДНЬОГО запиту й без api() (відмова з кодом)", () => {
  assert.match(appJs, /restartStep\(\{ prevBoot, target, startedAt, now: Date\.now\(\) \}, o\)/);
  assert.match(appJs, /const prevBoot = \(fresh \|\| info\)\.boot;/);
  assert.match(appJs, /updateFetch\('\/api\/update-apply'/);
  assert.match(appJs, /location\.reload\(\)/);
  assert.match(appJs, /setInterval\(pollUpdate, UPDATE_POLL_MS\)/);
});

/* ── опис змін ───────────────────────────────────────────────────────────── */

test("notesToBlocks: заголовки ###, пункти '- ' і абзаци розпізнано; текст НЕ екранується в моделі", () => {
  const body = "### Додано\n- перший пункт\n* другий <b>пункт</b>\n\nпросто рядок\n";
  assert.deepEqual(bodyToBlocks(body), [
    { kind: "h", text: "Додано" },
    { kind: "li", text: "перший пункт" },
    { kind: "li", text: "другий <b>пункт</b>" },
    { kind: "p", text: "просто рядок" },
  ]);
  const out = notesToBlocks([{ version: "0.2.0", date: "11.11.2026", body }, null, "x"]);
  assert.equal(out.length, 1);
  assert.equal(out[0].version, "0.2.0");
  assert.deepEqual(notesToBlocks(null), []);
});

/* ⛔ Тіло CHANGELOG — звичайний текст із можливими `<`/`>`. У розмітку воно йде ЛИШЕ через `esc` (контроль C). */
const EVIL = "<img src=x onerror=alert(1)>";

test("опис змін: тіло, версія й дата з `<img onerror>` — текст, а не розмітка", () => {
  const html = updateNotesHTML({ sections: [{ version: `0.2.0${EVIL}`, date: `d${EVIL}`, body: `### ${EVIL}\n- ${EVIL}\n${EVIL}` }] });
  assert.doesNotMatch(html, /<img/i, "сирий <img потрапив у розмітку");
  assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;"), "екранований текст має бути видно");
  assert.ok((html.match(/&lt;img/g) || []).length >= 5, "версія, дата, заголовок, пункт і абзац — усі екрановані");
  const dlg = updateDialogHTML({ current: "0.1.0", latest: "0.2.0", sections: [{ version: "1", date: "2", body: `- ${EVIL}` }] });
  assert.doesNotMatch(dlg, /<img/i);
});

test("опис змін: тіло — саме текст у <li>/<p> (а не <pre> із сирим HTML); підряд пункти — один <ul>", () => {
  const html = updateNotesHTML({ sections: [{ version: "0.2.0", date: "11.11.2026", body: "### Додано\n- а\n- б\nабзац" }] });
  assert.equal((html.match(/<ul class="up-list">/g) || []).length, 1);
  assert.equal((html.match(/<li>/g) || []).length, 2);
  assert.match(html, /<h3 class="up-sec-h">0\.2\.0 · 11\.11\.2026<\/h3>/);
});

test("опис змін: sections:null — «завантажую»; відмова — «Опис змін зараз недоступний» + клас причини (невідома → error)", () => {
  setLang("uk");
  assert.match(updateNotesHTML({ sections: null }), /Завантажую опис змін/);
  for (const reason of REASONS_D) {
    const h = updateNotesHTML({ sections: [], reason });
    assert.match(h, /Опис змін зараз недоступний/);
    assert.ok(h.includes(`(${reason})`), reason);
  }
  assert.ok(updateNotesHTML({ sections: [], reason: "щось-нове" }).includes("(error)"));
  assert.ok(updateNotesHTML({ sections: [], reason: `<b>` }).includes("(error)"), "причина не повертається в розмітку сирою");
  assert.match(updateNotesHTML({ sections: [] }), /немає/);
});

/* ── діалог ──────────────────────────────────────────────────────────────── */

test("діалог: форма askForm — role=dialog, aria-modal, aria-labelledby; OK = button[type=submit][data-a=ok]; слот помилки й статусу", () => {
  setLang("uk");
  const h = updateDialogHTML({ current: "0.1.0", latest: "0.2.0", blocked: null, state: "ok" });
  assert.match(h, /<form class="cv-form up"[^>]*role="dialog" aria-modal="true" aria-labelledby="up-h"/);
  assert.match(h, /<h2 class="cv-form-h" id="up-h">/);
  const ok = /<button type="submit" data-a="ok"[^>]*>/.exec(h)[0];
  assert.doesNotMatch(ok, /disabled/, "без blocked кнопка жива");
  assert.match(h, /data-form-error hidden/);
  assert.match(h, /data-up-status/);
  assert.match(h, /data-up-notes/);
  assert.match(h, /data-a="cancel" data-autofocus/, "фокус — на «Скасувати»");
  assert.match(h, /З версії 0\.1\.0 на 0\.2\.0/);
  assert.doesNotMatch(h, /class="up-why"/);
});

test("діалог: blocked — «Оновити» disabled, причина видима (.up-why) і привʼязана aria-describedby; команда має data-copy", () => {
  setLang("uk");
  const h = updateDialogHTML({ current: "0.1.0", latest: "0.2.0", blocked: "dirty" });
  const ok = /<button type="submit" data-a="ok"[^>]*>/.exec(h)[0];
  assert.match(ok, /disabled/);
  assert.match(ok, /aria-describedby="up-why"/);
  assert.match(h, /class="up-why" id="up-why"/);
  assert.match(h, /<code>git stash<\/code>/);
  assert.match(h, /data-copy="git stash"/);
  const d = updateDialogHTML({ current: "0.1.0", latest: "0.2.0", blocked: "diverged" });
  assert.match(d, /data-copy="git merge v0\.2\.0"/);
  const w = updateDialogHTML({ current: "0.1.0", latest: "0.2.0", blocked: "worktree" });
  assert.doesNotMatch(w, /data-copy/, "без команди — без кнопки копіювання");
  assert.match(w, /class="up-why"/);
});

test("діалог: restartFailed — «Перезапустіть Deai Canvas вручну» (uk) / «Restart Deai Canvas manually» (en), без «Оновити»", () => {
  for (const [lang, re] of [["uk", /Перезапустіть Deai Canvas вручну/], ["en", /Restart Deai Canvas manually/]]) {
    setLang(lang);
    const h = updateDialogHTML({ current: "0.2.0", latest: "0.2.0", restartFailed: true });
    assert.match(h, re, lang);
    assert.match(h, /role="alert"/);
    const ok = /<button type="submit" data-a="ok"[^>]*>/.exec(h)[0];
    assert.match(ok, /hidden/);
    assert.match(ok, /disabled/);
  }
  setLang("uk");
});

test("діалог: applying — aria-busy, «Оновлюю…», кнопка вимкнена; error показано в слоті", () => {
  setLang("uk");
  const h = updateDialogHTML({ current: "0.1.0", latest: "0.2.0", applying: true, error: `x${EVIL}` });
  assert.match(h, /aria-busy="true"/);
  assert.match(h, /data-up-status role="status">Оновлюю…/);
  assert.match(/<button type="submit" data-a="ok"[^>]*>/.exec(h)[0], /disabled/);
  assert.doesNotMatch(h, /<img/i, "помилка теж екранується");
});

test("діалог: дані з сервера екрануються (версії, код причини, стан)", () => {
  const h = updateDialogHTML({ current: EVIL, latest: EVIL, blocked: `<script>`, state: "offline", sections: null });
  assert.doesNotMatch(h, /<img|<script/i);
  assert.match(h, /Остання перевірка|Last check/);
});

test("пігулка: data-act=update, підпис з версією, іконка; restart — інший підпис і попередження", () => {
  setLang("uk");
  const h = updatePillHTML({ id: "update", version: "0.2.0", restart: false });
  assert.match(h, /class="ctl ctl--out upd-pill" data-act="update"/);
  assert.match(h, /Оновлення 0\.2\.0/);
  assert.match(h, /<svg/);
  assert.equal(updatePillHTML(undefined), "");
  const r = updatePillHTML({ id: "update", version: "0.2.0", restart: true });
  assert.match(r, /Потрібен перезапуск/);
  assert.match(updatePillHTML({ id: "update", version: `<i>`, restart: false }), /&lt;i&gt;/);
});

test("i18n: ключі up* є в обох мовах з однаковим типом", () => {
  const ups = Object.keys(DICT.uk).filter((k) => k.startsWith("up"));
  assert.ok(ups.length >= 40, `ключів лише ${ups.length}`);
  for (const k of ups) {
    assert.ok(DICT.en[k] !== undefined, `en.${k}`);
    assert.equal(typeof DICT.en[k], typeof DICT.uk[k], k);
  }
  for (const k of Object.keys(DICT.en).filter((x) => x.startsWith("up"))) assert.ok(DICT.uk[k] !== undefined, `uk.${k}`);
});

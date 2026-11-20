import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { setLang } from "../app/i18n.js";
import { agentsActsHTML, agentsBodyHTML, agentsKind, canUpdate } from "../app/agents-view.js";

test.beforeEach(() => setLang("uk"));

const BLOCK = "<!-- deai:begin v0.31.0 · x -->\n## Tasks\n<!-- deai:end -->\n";
const FILE = { ok: true, path: "/u/space/AGENTS.md", exists: true, hasBlock: true, outdated: false, newer: false,
  version: "0.31.0", fileVersion: "0.31.0", block: BLOCK, own: "\n## Team\n- note\n" };
const text = (h) => h.replace(/<[^>]*>/g, "");
const btn = (h, v) => new RegExp(`<button[^>]*data-th="ag" data-v="${v}"[^>]*>`).exec(h)?.[0] ?? null;

test("canUpdate: лише застарілий або файл без блока; новіший — ні; нема файла — ні", () => {
  assert.equal(canUpdate({ ...FILE, outdated: true }), true);
  assert.equal(canUpdate({ ...FILE, hasBlock: false, block: null }), true);
  assert.equal(canUpdate(FILE), false);
  assert.equal(canUpdate({ ...FILE, newer: true }), false);
  assert.equal(canUpdate({ ...FILE, newer: true, outdated: true }), false, "новіший ніколи не оновлюється, навіть якщо відповідь суперечлива");
  assert.equal(canUpdate({ exists: false }), false);
  assert.equal(canUpdate(null), false);
});

test("agentsKind: loading / error / nofolder / nofile / file", () => {
  assert.equal(agentsKind(null), "loading");
  assert.equal(agentsKind({ loading: true }), "loading");
  assert.equal(agentsKind({ failed: { code: "no-folder" } }), "nofolder");
  assert.equal(agentsKind({ failed: { code: "x" } }), "error");
  assert.equal(agentsKind({ exists: false }), "nofile");
  assert.equal(agentsKind(FILE), "file");
});

test("актуальний: «Скопіювати» активна, «Оновити з шаблону» неактивна, плашки нема, обидві частини переглядача", () => {
  const acts = agentsActsHTML(FILE);
  assert.doesNotMatch(btn(acts, "copy"), /disabled/);
  assert.match(btn(acts, "update"), /disabled/);
  const h = agentsBodyHTML(FILE);
  assert.doesNotMatch(h, /class="note"/);
  assert.match(h, /<div class="ag-bar">[^]*?<span>\/u\/space\/AGENTS\.md<\/span>/);
  assert.ok(btn(h, "copypath"), "копіювати шлях");
  assert.match(h, /<div class="ag-part"><div class="ag-g">З шаблону · Deai 0\.31\.0<\/div><pre role="region" tabindex="0" aria-label="З шаблону · Deai 0\.31\.0">/);
  assert.match(h, /<div class="ag-part ag-own"><div class="ag-g">Ваше · не чіпається<\/div><pre role="region" tabindex="0" aria-label="Ваше · не чіпається">\n## Team/);
});

test("застарілий: плашка з версіями й кнопкою, «Оновити» в голові активна", () => {
  const a = { ...FILE, outdated: true, fileVersion: "0.30.0" };
  assert.doesNotMatch(btn(agentsActsHTML(a), "update"), /disabled/);
  const h = agentsBodyHTML(a);
  assert.match(h, /<div class="note" role="status">[^]*?<p>Шаблон Deai 0\.31\.0 новіший за цей файл \(0\.30\.0\)\.<\/p>/);
  assert.doesNotMatch(btn(h, "update"), /disabled/);
});

test("новіший: плашка «оновіть Deai», обидві кнопки «Оновити» неактивні", () => {
  const a = { ...FILE, newer: true, fileVersion: "9.9.9" };
  assert.match(btn(agentsActsHTML(a), "update"), /disabled/);
  const h = agentsBodyHTML(a);
  assert.match(h, /<p>Цей блок записав новіший Deai \(9\.9\.9\) — оновіть Deai\.<\/p>/);
  assert.match(btn(h, "update"), /disabled/);
  assert.match(h, /З шаблону · Deai 9\.9\.9/, "ліва колонка — версія файла, а не поточна");
});

test("без блока: «Оновити» активна, частини «З шаблону» нема, весь текст — «Ваше»", () => {
  const a = { ...FILE, hasBlock: false, block: null, fileVersion: null, own: "# Мій файл\n" };
  assert.doesNotMatch(btn(agentsActsHTML(a), "update"), /disabled/);
  const h = agentsBodyHTML(a);
  assert.doesNotMatch(h, /З шаблону/);
  assert.match(h, /ag-own[^]*# Мій файл/);
});

test("порожнє «Ваше» (лише пробіли й переводи рядків) — частину не показуємо", () => {
  assert.doesNotMatch(agentsBodyHTML({ ...FILE, own: "\n" }), /ag-own/);
  assert.doesNotMatch(agentsBodyHTML({ ...FILE, own: "  \n\t" }), /ag-own/);
  assert.match(agentsBodyHTML({ ...FILE, own: "x" }), /ag-own/);
});

test("нема файла: «AGENTS.md ще нема» + «Створити»; голова без кнопок", () => {
  const a = { exists: false, hasBlock: false, path: "/u/space/AGENTS.md" };
  assert.equal(agentsActsHTML(a), "");
  const h = agentsBodyHTML(a);
  assert.match(h, /AGENTS\.md ще нема/);
  assert.ok(btn(h, "create"));
  assert.doesNotMatch(h, /class="ag"/);
});

test("нема теки: повідомлення без жодної кнопки", () => {
  const a = { failed: { code: "no-folder" } };
  assert.equal(agentsActsHTML(a), "");
  const h = agentsBodyHTML(a);
  assert.equal(text(h).trim(), "У цього простору нема теки");
  assert.doesNotMatch(h, /<button/);
});

test("збій читання: повідомлення й «Спробувати ще»; завантаження: статус", () => {
  assert.ok(btn(agentsBodyHTML({ failed: { code: "boom" } }), "retry"));
  assert.match(agentsBodyHTML({ loading: true }), /role="status"/);
  assert.equal(agentsActsHTML({ loading: true }), "");
});

test("екранування: вміст файла, шлях і версії не стають розміткою", () => {
  const evil = '<img src=x onerror=alert(1)>&"\'';
  const h = agentsBodyHTML({ ...FILE, outdated: true, block: evil, own: evil, path: evil, fileVersion: evil, version: evil });
  assert.doesNotMatch(h, /<img/);
  assert.ok(h.includes("&lt;img src=x onerror=alert(1)&gt;"));
  assert.doesNotMatch(h, /onerror=alert\(1\)>/);
});

test("busy: кнопки запису вимкнені", () => {
  assert.match(btn(agentsActsHTML({ ...FILE, outdated: true }, true), "update"), /disabled/);
  assert.match(btn(agentsBodyHTML({ exists: false }, true), "create"), /disabled/);
  assert.match(btn(agentsBodyHTML({ ...FILE, outdated: true }, true), "update"), /disabled/);
});

test("en: ті самі стани англійською", () => {
  setLang("en");
  const h = agentsBodyHTML({ ...FILE, outdated: true, fileVersion: "0.30.0" });
  assert.match(h, /Deai template 0\.31\.0 is newer than this file \(0\.30\.0\)\./);
  assert.match(agentsBodyHTML({ exists: false }), /AGENTS\.md doesn.t exist yet/);
});

test("a11y: прокручувані частини файла фокусовні й мають імʼя; код «unreadable» — стан помилки з «Спробувати ще»", () => {
  const h = agentsBodyHTML(FILE);
  assert.match(h, /<pre role="region" tabindex="0" aria-label="З шаблону · Deai 0\.31\.0">/);
  assert.match(h, /<pre role="region" tabindex="0" aria-label="Ваше · не чіпається">/);
  setLang("en");
  assert.match(agentsBodyHTML(FILE), /<pre role="region" tabindex="0" aria-label="From template · Deai 0\.31\.0">/);
  setLang("uk");
  assert.equal(agentsKind({ failed: { code: "unreadable" } }), "error");
  assert.ok(btn(agentsBodyHTML({ failed: { code: "unreadable" } }), "retry"));
  assert.match(agentsBodyHTML({ failed: { code: "unreadable" } }), /role="alert"/);
});

test("блоки файла: role=region і видимий :focus-visible на pre (токени, без колірних літералів)", () => {
  const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8");
  const m = css.match(/\.ag pre:focus-visible\{([^}]*)\}/);
  assert.ok(m, "правило :focus-visible для .ag pre");
  assert.match(m[1], /outline:\s*2px solid var\(--sel\)/);
  assert.doesNotMatch(m[1], /#[0-9a-f]{3,8}\b|rgb|hsl|oklch/i);
});

/* ── «Перший запуск» (0.33.0): над файлом — як запустити агента й чи прочитає його Claude Code ───────────── */
const A = (claude, o = {}) => ({ exists: true, hasBlock: true, outdated: false, newer: false, version: "0.33.0", fileVersion: "0.33.0",
  block: "b", own: "", text: "t", path: "/Users/a/deai-work/p/AGENTS.md", claude, ...o });

test("AGENTS.md: рядок «Запуск агента» з командою cd <тека> && claude і копіюванням", () => {
  const h = agentsBodyHTML(A({ state: "ok", path: "/Users/a/deai-work/p/CLAUDE.md" }));
  assert.match(h, /<div class="set-rows fr-run">/);
  assert.match(h, /<code class="cn-code" id="fr-run-cmd">cd \/Users\/a\/deai-work\/p &amp;&amp; claude<\/code>/);
  assert.match(h, /data-th="ag" data-v="runcopy"/);
  assert.ok(h.indexOf("fr-run") < h.indexOf('class="ag"'), "рядки — над файлом");
});

test("AGENTS.md: «Claude Code» — галочка для ok; «Підключити» для missing і no-import; unreadable — без кнопки", () => {
  const ok = agentsBodyHTML(A({ state: "ok" }));
  assert.match(ok, /data-claude="ok"><span class="fr-ic fr-ic--ok">/);
  assert.doesNotMatch(ok, /data-v="claude"/);
  for (const state of ["missing", "no-import"]) {
    assert.match(agentsBodyHTML(A({ state })), new RegExp(`data-claude="${state}"[\\s\\S]*data-v="claude"[^>]*>Підключити<`));
  }
  assert.match(agentsBodyHTML(A({ state: "missing" }), true), /data-v="claude" disabled/);
  const un = agentsBodyHTML(A({ state: "unreadable" }));
  assert.match(un, /не читається/);
  assert.doesNotMatch(un, /data-v="claude"/);
});

test("AGENTS.md: файла ще нема — рядки є й над «Створити»; старий сервер без `claude` — лише «Запуск агента»", () => {
  const nofile = agentsBodyHTML(A({ state: "missing" }, { exists: false, hasBlock: false, text: "", block: null }));
  assert.match(nofile, /fr-run[\s\S]*data-v="create"/);
  const old = agentsBodyHTML(A(undefined));
  assert.match(old, /fr-run-cmd/);
  assert.doesNotMatch(old, /data-claude/);
});

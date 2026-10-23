/**
 * Поведінка проводки довіри з `app.js` (Deai 0.7.0, етап 3c, Task 7): `openTrust`, `untrustFlow`, `trustPost`, `connTrust`,
 * `cnDrawerUntrust`, гілки `connAction` і `wireCnDrawer`. Функції ЗІБРАНО З ДЖЕРЕЛА й запущено з підставними залежностями
 * (DOM нема) — як `publishAction` у `spaces-wiring.test.mjs`: регекспи `connections-wiring.test.mjs` бачать ТЕКСТ коду, а тут
 * видно, ЩО він робить: що йде в запит, коли діалог закривається, чи лишається позначка «Забрати довіру» після успіху.
 * Правила (`trustDialogHTML`, `refusalView`, `t`, `modName`) — справжні; решта (`askForm`, `formApi`, `trustPost`, `toast`…) —
 * підставні й записують виклики.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { t } from "../app/i18n.js";
import { refusalView } from "../app/connections-model.js";
import { modName, roleTitle } from "../app/connections-view.js";
import { TRUST_POST_TIMEOUT_MS, trustDialogHTML } from "../app/trust-view.js";

const src = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

/** Повний текст функції `name` (з сигнатурою) до парної `}`. */
function fnSrc(name) {
  const m = new RegExp(`(?:async )?function ${name}\\(`).exec(src);
  assert.ok(m, `функції ${name} нема`);
  const open = src.indexOf("{", src.indexOf(")", m.index));
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) return src.slice(m.index, i + 1); }
  }
  throw new Error(`немає закриття для ${name}`);
}
/** Збирає функції `names` з app.js й віддає їх обʼєктом; `deps` — підставні залежності (імена — як в app.js), `prelude` — код перед ними. */
function build(names, deps, prelude = "") {
  const keys = Object.keys(deps);
  const code = `${prelude}\n${names.map(fnSrc).join("\n")}\nreturn { ${names.join(", ")} };`;
  return new Function(...keys, code)(...keys.map((k) => deps[k]));
}

const ENTRY = { id: "acme", name: "Acme", roles: ["publish"], enabled: false, custom: true };
const trustData = (over = {}) => ({
  id: "acme", name: "Acme", version: "1", roles: ["publish"], path: "~/w/acme", state: "untrusted", record: false,
  hash: "aa".repeat(32), settings: [], files: [{ path: "module.json", size: 10, change: "new" }], removed: [],
  total: { files: 1, bytes: 10 }, ...over,
});
const refusal = (code, message = "") => Object.assign(new Error(message), { code });

/** Фальшивий діалог `askForm`: збирає розмітку (`build`), монтує (`onMount`), далі сценарій веде «людину». */
function makeAskForm(scripts) {
  const dialogs = [];
  const askForm = async (buildFn, opts) => {
    const attrs = {};
    const listeners = new Map();
    const dlg = { html: buildFn(), opts, attrs, result: undefined, cancelClicks: 0, wait: { hidden: true }, waitLog: [] };
    const cancel = { click: () => { dlg.cancelClicks += 1; if (attrs["aria-busy"] !== "true") dlg.result = null; } };
    const untrustBtn = {
      addEventListener: (type, fn) => listeners.set(type, fn),
      click: () => listeners.get("click")?.(),
    };
    const waitWatch = new Proxy(dlg.wait, { set(o, k, v) { if (k === "hidden") dlg.waitLog.push(v); o[k] = v; return true; } });
    const form = {
      getAttribute: (k) => attrs[k] ?? null,
      /* «Забрати довіру» є в DOM лише коли розмітка її містить (запис довіри) — як у справжньому діалозі. */
      querySelector: (sel) => ({ '[data-a="cancel"]': cancel, "[data-tr-wait]": waitWatch,
        '[data-tr="untrust"]': dlg.html.includes('data-tr="untrust"') ? untrustBtn : null })[sel] ?? null,
    };
    const ctl = { form };
    dlg.form = form;
    dlg.untrustBtn = untrustBtn;
    /* Відправка, як у справжньому `askForm`: форма «зайнята» (`aria-busy`) на час `onSubmit`; рядок — відмова, діалог лишається. */
    dlg.submit = async () => {
      attrs["aria-busy"] = "true";
      let err;
      try { err = await opts.onSubmit({}, ctl); } catch (e) { err = String(e?.message ?? e); }
      delete attrs["aria-busy"];
      if (err) { dlg.error = err; return err; }
      dlg.result = {};
      return undefined;
    };
    dialogs.push(dlg);
    opts.onMount?.(form, ctl);
    const script = scripts[dialogs.length - 1];
    assert.ok(script, `несподіваний показ діалогу №${dialogs.length}`);
    await script(dlg);
    return dlg.result === undefined ? null : dlg.result;
  };
  return { askForm, dialogs };
}

/** `openTrust` з підставними залежностями; `log` пише всі побічні виклики в порядку. */
function trustEnv({ scripts, get = async () => ({ trust: trustData() }), post = async () => ({ ok: true }) , untrust = async () => true } = {}) {
  const log = [];
  const { askForm, dialogs } = makeAskForm(scripts);
  const formCalls = [];
  const postCalls = [];
  const deps = {
    t, refusalView, modName, getLang: () => "uk", CSS: { escape: (s) => s },
    trustDialogHTML,
    homeNode: () => null,
    askForm,
    formApi: async (url) => { formCalls.push(url); return get(formCalls.length - 1, url); },
    trustPost: async (body) => { postCalls.push(body); return post(postCalls.length - 1, body); },
    tell: (m) => log.push(["tell", m]),
    toast: (m) => log.push(["toast", m]),
    afterModulesChange: async () => { log.push(["afterModulesChange"]); },
    untrustFlow: async (e, s) => { log.push(["untrustFlow", e.id, s]); return untrust(); },
  };
  const { openTrust } = build(["openTrust"], deps);
  return { openTrust, log, dialogs, formCalls, postCalls };
}

test("openTrust, успіх: GET свіжих даних у зафіксований простір, POST {space,id,hash,lang}, тост, перечитування модулів, true", async () => {
  const env = trustEnv({ scripts: [async (dlg) => { await dlg.submit(); }] });
  assert.equal(await env.openTrust(ENTRY, "alpha"), true);
  assert.deepEqual(env.formCalls, ["/api/module-trust?space=alpha&id=acme"]);
  assert.deepEqual(env.postCalls, [{ space: "alpha", id: "acme", hash: "aa".repeat(32), lang: "uk" }]);
  assert.deepEqual(env.log, [["toast", t("cnToastTrusted", "Acme")], ["afterModulesChange"]], "тост — до перечитування");
  assert.match(env.dialogs[0].html, /Довіритись модулю «Acme»\?/);
  assert.doesNotMatch(env.dialogs[0].html, /tr-reopened/);
  assert.deepEqual(env.dialogs[0].waitLog, [false, true], "рядок «Підтвердіть у системному вікні…» — лише на час запиту");
  assert.equal(env.dialogs[0].wait.hidden, true);
});

test("openTrust: простір і id у запиті екрануються (`encodeURIComponent`) — id/простір з диска не ламають адресу", async () => {
  const env = trustEnv({ scripts: [async (dlg) => { dlg.result = null; }] });
  await env.openTrust({ ...ENTRY, id: "a b&c" }, "sp/ace?");
  assert.deepEqual(env.formCalls, ["/api/module-trust?space=sp%2Face%3F&id=a%20b%26c"]);
});

test("openTrust, «Скасувати»: нічого не запитано, тосту й перечитування нема, false", async () => {
  const env = trustEnv({ scripts: [async (dlg) => { dlg.form.querySelector('[data-a="cancel"]').click(); }] });
  assert.equal(await env.openTrust(ENTRY, "alpha"), false);
  assert.deepEqual(env.postCalls, []);
  assert.deepEqual(env.log, []);
});

test("openTrust, module-changed: діалог закривається й відкривається ЗНОВУ зі свіжими даними й рядком угорі; другий POST — зі свіжим відбитком", async () => {
  const hashes = ["11".repeat(32), "22".repeat(32)];
  const env = trustEnv({
    get: async (i) => ({ trust: trustData({ hash: hashes[i] }) }),
    post: async (i) => { if (i === 0) throw refusal("module-changed"); return { ok: true }; },
    scripts: [async (dlg) => { assert.equal(await dlg.submit(), undefined, "module-changed — не текст у діалозі"); }, async (dlg) => { await dlg.submit(); }],
  });
  assert.equal(await env.openTrust(ENTRY, "alpha"), true);
  assert.equal(env.dialogs.length, 2);
  assert.doesNotMatch(env.dialogs[0].html, /tr-reopened/);
  assert.match(env.dialogs[1].html, /<p class="tr-reopened" role="status">/, "повторне відкриття — з рядком про зміну");
  assert.equal(env.formCalls.length, 2, "дані перечитано");
  assert.deepEqual(env.postCalls.map((b) => b.hash), hashes, "другий запит несе відбиток нового вигляду теки");
  assert.deepEqual(env.log, [["toast", t("cnToastTrusted", "Acme")], ["afterModulesChange"]], "тост і перечитування — один раз, після успіху");
});

test("openTrust, module-changed знову й знову: цикл не зупиняється сам — кожне відкриття свіже, `reopened` лишається", async () => {
  const env = trustEnv({
    post: async (i) => { if (i < 2) throw refusal("module-changed"); return { ok: true }; },
    scripts: [async (d) => { await d.submit(); }, async (d) => { await d.submit(); }, async (d) => { await d.submit(); }],
  });
  assert.equal(await env.openTrust(ENTRY, "alpha"), true);
  assert.equal(env.dialogs.length, 3);
  assert.match(env.dialogs[2].html, /tr-reopened/);
});

test("openTrust, інша відмова: текст у діалозі (діалог лишається), рядок очікування сховано, тосту й перечитування нема", async () => {
  const env = trustEnv({
    post: async () => { throw refusal("trust-declined", "declined by user"); },
    scripts: [async (dlg) => {
      const err = await dlg.submit();
      assert.equal(err, `${t("cnRefDeclined")} — declined by user`);
      assert.equal(dlg.result, undefined, "діалог не закрито");
      dlg.form.querySelector('[data-a="cancel"]').click();
    }],
  });
  assert.equal(await env.openTrust(ENTRY, "alpha"), false);
  assert.deepEqual(env.log, [], "ні тосту, ні afterModulesChange");
  assert.deepEqual(env.dialogs[0].waitLog, [false, true], "рядок про системне вікно сховано й після відмови");
  assert.equal(env.dialogs.length, 1, "діалог не відкрито знову");
});

test("openTrust: тайм-аут запиту — текст про тайм-аут у діалозі, а не мовчання", async () => {
  const env = trustEnv({
    post: async () => { throw refusal("timeout"); },
    scripts: [async (dlg) => { assert.equal(await dlg.submit(), t("cnTimeout")); dlg.result = null; }],
  });
  assert.equal(await env.openTrust(ENTRY, "alpha"), false);
});

test("openTrust, «Забрати довіру»: позначка + «Скасувати» → діалог закрито, далі untrustFlow(entry, space), без тосту «Довірено»; false", async () => {
  const env = trustEnv({
    get: async () => ({ trust: trustData({ record: true, state: "trusted" }) }),
    scripts: [async (dlg) => { dlg.untrustBtn.click(); }],
  });
  assert.equal(await env.openTrust(ENTRY, "alpha"), false);
  assert.deepEqual(env.log, [["untrustFlow", "acme", "alpha"]]);
  assert.equal(env.dialogs[0].cancelClicks, 1);
  assert.deepEqual(env.postCalls, [], "довіру не видано");
  assert.match(env.dialogs[0].html, /data-tr="untrust"/);
});

test("openTrust, «Забрати довіру» під час запиту (aria-busy) нічого не позначає: після успішної довіри питання про відкликання НЕ зʼявляється", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const env = trustEnv({
    get: async () => ({ trust: trustData({ record: true, state: "changed" }) }),
    post: async () => { await gate; return { ok: true }; },
    scripts: [async (dlg) => {
      const sent = dlg.submit();
      dlg.untrustBtn.click();          // форма «зайнята»: клік мусить бути проігнорований
      assert.equal(dlg.cancelClicks, 0, "«Скасувати» під час запиту не чіпаємо");
      release();
      await sent;
    }],
  });
  assert.equal(await env.openTrust(ENTRY, "alpha"), true);
  assert.deepEqual(env.log, [["toast", t("cnToastTrusted", "Acme")], ["afterModulesChange"]], "untrustFlow не кликано");
});

test("openTrust: збій читання свіжих даних — повідомлення, діалог не показано; порожня відповідь — тихо false", async () => {
  const bad = trustEnv({ get: async () => { throw refusal("unknown-module"); }, scripts: [] });
  assert.equal(await bad.openTrust(ENTRY, "alpha"), false);
  assert.deepEqual(bad.log, [["tell", t("cnRefUnknownModule")]]);
  assert.equal(bad.dialogs.length, 0);
  const empty = trustEnv({ get: async () => ({}), scripts: [] });
  assert.equal(await empty.openTrust(ENTRY, "alpha"), false);
  assert.deepEqual(empty.log, []);
  assert.equal(empty.dialogs.length, 0);
});

test("openTrust, refused: діалог без «Довіряю» (лише причина й «Закрити») — розмітка з сервера доходить до askForm як є", async () => {
  const env = trustEnv({
    get: async () => ({ trust: { id: "acme", name: "Acme", version: "1", roles: ["publish"], path: "~/w/acme", state: "refused", record: false,
      refused: { code: "symlink", detail: "alias.py: symbolic link" } } }),
    scripts: [async (dlg) => { dlg.form.querySelector('[data-a="cancel"]').click(); }],
  });
  assert.equal(await env.openTrust(ENTRY, "alpha"), false);
  assert.doesNotMatch(env.dialogs[0].html, /data-a="ok"/);
  assert.match(env.dialogs[0].html, /У теці є символьне посилання/);
});

test("openTrust: запасний відкривач фокуса — кнопка ТІЄЇ Ж картки в екрані «Підключення» (не вимкнена)", async () => {
  const queries = [];
  const deps = {
    t, refusalView, modName, getLang: () => "uk", CSS: { escape: (s) => `<${s}>` }, trustDialogHTML,
    homeNode: () => ({ querySelector: (sel) => { queries.push(sel); return { sel }; } }),
    askForm: async (b, opts) => { queries.push(opts.focusBack()); return null; },
    formApi: async () => ({ trust: trustData() }), trustPost: async () => ({}), tell() {}, toast() {},
    afterModulesChange: async () => {}, untrustFlow: async () => true,
  };
  await build(["openTrust"], deps).openTrust(ENTRY, "alpha");
  assert.deepEqual(queries[0], '[data-cn][data-id="<acme>"]:not([disabled])');
  assert.deepEqual(queries[1], { sel: '[data-cn][data-id="<acme>"]:not([disabled])' });
});

/* ── trustPost ── */

function postEnv(api) {
  const timers = [];
  const cleared = [];
  const deps = {
    api, TRUST_POST_TIMEOUT_MS, AbortController,
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout: (id) => cleared.push(id),
  };
  return { ...build(["trustPost"], deps), timers, cleared };
}

test("trustPost: POST JSON на /api/module-trust зі СТЕЛЕЮ 150 с (не 20 с `formApi`), таймер знімається після успіху й після відмови", async () => {
  const calls = [];
  const ok = postEnv(async (path, opts) => { calls.push([path, opts]); return { ok: true }; });
  assert.deepEqual(await ok.trustPost({ space: "a", id: "b" }), { ok: true });
  assert.equal(calls[0][0], "/api/module-trust");
  assert.equal(calls[0][1].method, "POST");
  assert.deepEqual(calls[0][1].headers, { "Content-Type": "application/json" });
  assert.equal(calls[0][1].body, JSON.stringify({ space: "a", id: "b" }));
  assert.ok(calls[0][1].signal, "запит можна обірвати");
  assert.deepEqual(ok.timers.map((x) => x.ms), [TRUST_POST_TIMEOUT_MS]);
  assert.deepEqual(ok.cleared, [1], "таймер знято після успіху");
  const bad = postEnv(async () => { throw refusal("trust-declined", "no"); });
  await assert.rejects(bad.trustPost({}), (e) => e.code === "trust-declined" && e.message === "no", "чужа відмова йде як є");
  assert.deepEqual(bad.cleared, [1], "таймер знято й після відмови");
});

test("trustPost: стеля спрацювала — запит обірвано, відмова з code 'timeout' (текст cnTimeout), таймер знято", async () => {
  const env = postEnv((path, opts) => new Promise((_, reject) => {
    opts.signal.addEventListener("abort", () => reject(Object.assign(new Error("The operation was aborted"), { name: "AbortError" })));
  }));
  const p = env.trustPost({ space: "a", id: "b" });
  env.timers[0].fn();
  await assert.rejects(p, (e) => e.code === "timeout");
  assert.equal(refusalView(await p.catch((e) => e)).key, "cnTimeout");
  assert.deepEqual(env.cleared, [1]);
});

/* ── «Забрати довіру» ── */

function untrustEnv({ yes = true, post = async () => ({ ok: true }) } = {}) {
  const log = [];
  const deps = {
    t, refusalView, modName, roleTitle,
    askYesNo: async (q, o) => { log.push(["ask", q, o]); return yes; },
    postForm: async (path, body) => { log.push(["post", path, body]); return post(); },
    tell: (m) => log.push(["tell", m]),
    toast: (m) => log.push(["toast", m]),
    afterModulesChange: async () => { log.push(["afterModulesChange"]); },
  };
  return { ...build(["untrustFlow"], deps), log };
}

test("untrustFlow: небезпечне питання (для ввімкненого — з ролями, що перестануть працювати), далі POST у ЗАФІКСОВАНИЙ простір, тост, перечитування", async () => {
  const env = untrustEnv();
  const entry = { id: "acme", name: "Acme", roles: ["publish", "comments"], enabled: true };
  assert.equal(await env.untrustFlow(entry, "alpha"), true);
  const [ask, post, toast, after] = env.log;
  assert.equal(ask[1], [t("cnUntrustAsk", "Acme"), t("cnUntrustRole", ["publish", "comments"].map(roleTitle).join(", ")), t("cnUntrustKeeps")].join("\n\n"));
  assert.deepEqual(ask[2], { yes: t("cnUntrust"), danger: true });
  assert.deepEqual(post, ["post", "/api/module-untrust", { space: "alpha", id: "acme" }]);
  assert.deepEqual(toast, ["toast", t("cnToastUntrusted", "Acme")]);
  assert.deepEqual(after, ["afterModulesChange"]);
  assert.equal(env.log.length, 4, "порядок: питання → запит → тост → перечитування");
});

test("untrustFlow: вимкнений модуль — без речення про ролі; «Ні» в питанні — нічого не йде, false", async () => {
  const off = untrustEnv();
  await off.untrustFlow({ id: "acme", name: "Acme", roles: ["publish"], enabled: false }, "alpha");
  assert.equal(off.log[0][1], [t("cnUntrustAsk", "Acme"), t("cnUntrustKeeps")].join("\n\n"));
  const no = untrustEnv({ yes: false });
  assert.equal(await no.untrustFlow({ id: "acme", name: "Acme", roles: ["publish"], enabled: true }, "alpha"), false);
  assert.deepEqual(no.log.map((x) => x[0]), ["ask"], "відмова людини — ні запиту, ні тосту, ні перечитування");
});

test("untrustFlow: відмова сервера — повідомлення людині, без тосту «Довіру забрано» й без перечитування модулів; false", async () => {
  const env = untrustEnv({ post: async () => { throw refusal("unknown-space"); } });
  assert.equal(await env.untrustFlow({ id: "acme", name: "Acme", roles: [], enabled: false }, "alpha"), false);
  assert.deepEqual(env.log.map((x) => x[0]), ["ask", "post", "tell"]);
  assert.equal(env.log[2][1], t("cnRefUnknownSpace"));
});

/* ── «Довіритись…» на картці ── */

function connTrustEnv({ moveSpaceTo = null, open = true } = {}) {
  const connState = { spaceId: "alpha" };
  const log = [];
  const deps = {
    connState,
    openTrust: async (e, s) => { log.push(["openTrust", e.id, s]); if (moveSpaceTo) connState.spaceId = moveSpaceTo; return false; },
    connOpen: () => open,
    refocusCard: (id, act) => log.push(["refocusCard", id, act]),
  };
  return { ...build(["connTrust"], deps), log };
}

test("connTrust: діалог — для простору сторінки НА МОМЕНТ КЛІКУ; після нього фокус на картку, лише поки сторінка той самий простір", async () => {
  const same = connTrustEnv();
  await same.connTrust(ENTRY);
  assert.deepEqual(same.log, [["openTrust", "acme", "alpha"], ["refocusCard", "acme", "trust"]]);
  const moved = connTrustEnv({ moveSpaceTo: "beta" });
  await moved.connTrust(ENTRY);
  assert.deepEqual(moved.log, [["openTrust", "acme", "alpha"]], "діалог ішов в alpha, хоч сторінка потім перейшла в beta; фокус на чужу картку не ставимо");
  const closed = connTrustEnv({ open: false });
  await closed.connTrust(ENTRY);
  assert.deepEqual(closed.log, [["openTrust", "acme", "alpha"]], "сторінки «Підключення» вже нема — фокусу нема куди");
});

/* ── панель ── */

function drawerEnv({ drawer, dismiss = true }) {
  const log = [];
  const deps = {
    initialDrawer: drawer, dismissResult: dismiss,
    untrustFlow: async (e, s) => { log.push(["untrustFlow", e.id, s]); },
  };
  const prelude = `let cnDrawer = initialDrawer;
    const dismissCnDrawer = async () => { if (dismissResult) cnDrawer = null; return dismissResult; };`;
  return { ...build(["cnDrawerUntrust"], deps, prelude), log };
}

test("cnDrawerUntrust: модуль і простір — з панелі ДО її закриття (після нього cnDrawer = null), далі untrustFlow", async () => {
  const env = drawerEnv({ drawer: { entry: ENTRY, spaceId: "alpha", busy: false } });
  await env.cnDrawerUntrust();
  assert.deepEqual(env.log, [["untrustFlow", "acme", "alpha"]]);
});

test("cnDrawerUntrust: людина лишила панель («Відкинути зміни?» — ні), панелі нема чи вона в запиті — untrustFlow не кликано", async () => {
  const keep = drawerEnv({ drawer: { entry: ENTRY, spaceId: "alpha", busy: false }, dismiss: false });
  await keep.cnDrawerUntrust();
  assert.deepEqual(keep.log, []);
  const none = drawerEnv({ drawer: null });
  await none.cnDrawerUntrust();
  assert.deepEqual(none.log, []);
  const busy = drawerEnv({ drawer: { entry: ENTRY, spaceId: "alpha", busy: "save" } });
  await busy.cnDrawerUntrust();
  assert.deepEqual(busy.log, [], "запит панелі не перебивається");
});

/* ── connAction / wireCnDrawer ── */

function actionEnv({ list = [ENTRY], busy = new Set(), drawer = null, dismiss = true, refreshTo = null } = {}) {
  const log = [];
  const connState = { list, busy, spaceId: "alpha" };
  const deps = {
    initialDrawer: drawer, dismissResult: dismiss, refreshTo, connState,
    loadConn: () => log.push(["loadConn"]), connCheck: (e) => log.push(["connCheck", e.id]),
    connOpen: () => true,
    openCnDrawer: (e, m) => log.push(["openCnDrawer", e.id, m]), connDisable: (e) => log.push(["connDisable", e.id]),
    connTrust: (e) => log.push(["connTrust", e]),
  };
  const prelude = `let cnDrawer = initialDrawer;
    const dismissCnDrawer = async () => { if (refreshTo) connState.list = refreshTo; if (dismissResult) cnDrawer = null; return dismissResult; };`;
  return { ...build(["connAction"], deps, prelude), log };
}

test("connAction: «Довіритись…» і «Чому не можна…» ведуть у connTrust з карткою зі списку; інші дії й чужі id — ні", async () => {
  for (const act of ["trust", "trustinfo"]) {
    const env = actionEnv();
    await env.connAction(act, "acme");
    assert.deepEqual(env.log, [["connTrust", ENTRY]], act);
  }
  const unknown = actionEnv();
  await unknown.connAction("trust", "nope");
  assert.deepEqual(unknown.log, [], "картки нема в списку");
  const busy = actionEnv({ busy: new Set(["acme"]) });
  await busy.connAction("trust", "acme");
  assert.deepEqual(busy.log, [], "дія над модулем у польоті ігнорується");
  const configure = actionEnv();
  await configure.connAction("configure", "acme");
  assert.deepEqual(configure.log, [["openCnDrawer", "acme", "edit"]], "контроль: інша дія — своя гілка, не connTrust");
});

test("connAction: відкрита панель спершу закривається (з питанням); людина лишила її — діалог довіри не відкривається; картка береться СВІЖА", async () => {
  const drawer = { id: "other", busy: false };
  const keep = actionEnv({ drawer, dismiss: false });
  await keep.connAction("trust", "acme");
  assert.deepEqual(keep.log, [], "«Відкинути зміни?» — ні: діалог довіри поверх панелі не відкриваємо");
  const fresh = { ...ENTRY, enabled: true };
  const go = actionEnv({ drawer, refreshTo: [fresh] });
  await go.connAction("trust", "acme");
  assert.deepEqual(go.log, [["connTrust", fresh]], "після питання — картка зі свіжого списку");
});

test("wireCnDrawer: «Забрати довіру» панелі → cnDrawerUntrust; вимкнена кнопка й чужий клік — ні; решта дій — як були", () => {
  const log = [];
  const handlers = new Map();
  const el = { addEventListener: (type, fn) => handlers.set(type, fn) };
  const deps = {
    requestCloseCnDrawer: () => log.push("close"), cnDrawerCheck: () => log.push("check"), toggleCnErase: (b) => log.push(["erase", b.k]),
    cnDrawerUntrust: () => log.push("untrust"), cnSubmit: () => {}, syncCnDrawer: () => {},
  };
  const { wireCnDrawer } = build(["wireCnDrawer"], deps);
  wireCnDrawer(el);
  const click = (b) => handlers.get("click")({ target: { closest: () => b } });
  click({ disabled: false, dataset: { cnDr: "untrust" } });
  click({ disabled: true, dataset: { cnDr: "untrust" } });
  click(null);
  click({ disabled: false, dataset: { cnDr: "close" } });
  click({ disabled: false, dataset: { cnDr: "check" } });
  click({ disabled: false, dataset: { cnDr: "erase" }, k: "token" });
  assert.deepEqual(log, ["untrust", "close", "check", ["erase", "token"]]);
});

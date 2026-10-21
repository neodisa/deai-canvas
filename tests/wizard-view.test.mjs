import assert from "node:assert/strict";
import test from "node:test";
import { getLang, setLang } from "../app/i18n.js";
import { wizardHTML } from "../app/wizard-view.js";

const CYR = /[а-яіїєґА-ЯІЇЄҐ]/;
const M = (id, roles, extra = {}) => ({ id, name: id, roles, enabled: false, status: "unchecked", settings: [], ...extra });
const LIST = [
  M("static-publish", ["publish"], { enabled: true, implicit: true, status: "ok",
    settings: [{ key: "folder", type: "path", value: "{space}/publish" }] }),
  M("vercel-publish", ["publish"]),
  M("css-tokens", ["tokens"]),
];
const V = (over = {}) => ({
  step: 1, created: false, busy: false,
  s1: { name: "Клієнт", color: "space-3", path: "~/deai-work/klient", folderFirst: false },
  s2: { list: LIST, failed: null, capsError: false, pick: new Set(["static-publish"]), path: "/p" },
  s3: { cards: [], offs: [], failed: null, loading: false },
  s4: { title: "", id: "", source: "empty", from: "", spaceName: "Клієнт", tasks: 0 },
  ...over,
});

test("смужка кроків: ol з чотирьох, aria-current лише на поточному, рядок «Крок N з 4»", () => {
  const h = wizardHTML(V({ step: 2 }));
  assert.match(h, /<div class="th-in wz" data-step="2">/);
  assert.match(h, /<ol class="wz-steps" aria-label="Кроки майстра">/);
  assert.equal((h.match(/<li class="wz-step/g) ?? []).length, 4);
  assert.equal((h.match(/aria-current="step"/g) ?? []).length, 1);
  assert.match(h, /wz-step--done[\s\S]*wz-step--cur[\s\S]*wz-step--todo/);
  assert.match(h, /Крок 2 з 4 · Модулі/);
  assert.match(h, /<h1 class="th-h wz-h" id="wz-h" tabindex="-1">Що підключити<\/h1>/);
});

test("крок 1 (новий): гачки форми простору, кружки, підказки теки, «Скасувати», «Далі»", () => {
  const h = wizardHTML(V());
  assert.match(h, /<form class="wz-form" data-wz-step="1" data-form="space" data-mode="new" novalidate>/);
  assert.match(h, /<input class="cn-inp" id="sp-name" name="name" type="text" value="Клієнт"/);
  assert.match(h, /<input class="cn-inp" id="sp-path" name="path" type="text" value="~\/deai-work\/klient"/);
  assert.match(h, /<input type="hidden" name="color" value="space-3">/);
  assert.equal((h.match(/class="cv-color" role="radio"/g) ?? []).length, 6);
  assert.match(h, /id="sp-found" role="status" hidden/);
  assert.match(h, /id="sp-registered" role="status" hidden/);
  assert.match(h, /<p class="wz-err" id="wz-err" role="alert" hidden><\/p>/);
  assert.match(h, /data-a="cancel"/);
  assert.match(h, /<button type="submit" class="ctl ctl--pri" data-a="ok">Далі/);
  assert.doesNotMatch(h, /data-wz="back"/);
});

test("крок 1: кружки — рівно один вибраний за токеном, він єдиний у Tab-порядку; невідомий колір → типовий", () => {
  const radios = (h) => [...h.matchAll(/<button type="button" class="cv-color" role="radio"[\s\S]*?<\/button>/g)].map((m) => m[0]);
  const read = (r, re) => re.exec(r)?.[1];
  const h = wizardHTML(V({ s1: { name: "", color: "space-4", path: "", folderFirst: false } }));
  const rs = radios(h);
  assert.deepEqual(rs.map((r) => read(r, /data-val="([^"]+)"/)), ["space-1", "space-2", "space-3", "space-4", "space-5", "space-6"]);
  assert.deepEqual(rs.map((r) => read(r, /aria-checked="([^"]+)"/)), ["false", "false", "false", "true", "false", "false"]);
  assert.deepEqual(rs.map((r) => read(r, /tabindex="([^"]+)"/)), ["-1", "-1", "-1", "0", "-1", "-1"]);
  rs.forEach((r, i) => assert.match(r, new RegExp(`style="background:var\\(--space-${i + 1}\\)"`)));
  for (const r of rs) assert.match(r, /aria-label="[^"]+"/, "кожен кружок має імʼя для читача");
  assert.match(h, /<input type="hidden" name="color" value="space-4">/);
  const bad = wizardHTML(V({ s1: { name: "", color: "red", path: "", folderFirst: false } }));
  assert.match(bad, /<input type="hidden" name="color" value="space-1">/);
  assert.equal((radios(bad).filter((r) => /aria-checked="true"/.test(r))).length, 1);
});

test("крок 1 після створення: режим правки — тека лише для читання з поясненням, замість «Скасувати» — «Закрити майстер»", () => {
  const h = wizardHTML(V({ created: true }));
  assert.match(h, /data-mode="edit"/);
  assert.match(h, /id="sp-path"[^>]*readonly/);
  assert.match(h, /Теку створеного простору не змінити/);
  assert.doesNotMatch(h, /data-a="cancel"/);
  assert.match(h, /data-wz="close"/);
  assert.match(h, />Простір<\/h1>/);
  /* Підказок «знайдено/зареєстровано» в режимі правки нема: `wireSpaceDialog(edit)` їх не проводить. */
  assert.doesNotMatch(h, /id="sp-found"|id="sp-registered"/);
  assert.match(h, /data-a="ok">Далі/);
});

test("крок 1 зайнятий: aria-busy, кнопки вимкнені, «Створюю…»", () => {
  const h = wizardHTML(V({ busy: "save" }));
  assert.match(h, /data-form="space" data-mode="new" novalidate aria-busy="true">/);
  assert.match(h, /data-a="ok" disabled>Створюю…/);
  assert.match(h, /data-a="cancel" disabled/);
  assert.match(h, /id="sp-name"[^>]*disabled/);
  assert.match(h, /id="sp-path"[^>]*disabled/);
  assert.equal((h.match(/class="cv-color" role="radio"[^>]*disabled/g) ?? []).length, 6, "кружки теж вимкнені");
});

test("крок 1 зайнятий після створення (правка): «Зберігаю…», «Закрити майстер» вимкнено", () => {
  const h = wizardHTML(V({ created: true, busy: "save" }));
  assert.match(h, /data-a="ok" disabled>Зберігаю…/);
  assert.match(h, /data-wz="close" disabled/);
});

test("крок 2: секції-fieldset з legend, радіо на модуль + «Без модуля», вибране з pick, «типово», «замість»", () => {
  const h = wizardHTML(V({ step: 2 }));
  assert.match(h, /<fieldset class="wz-sec"><legend class="cn-sec-h">Публікація<\/legend>/);
  assert.match(h, /<input type="radio" id="wz-o-0-0" name="wz-r-0" value="static-publish" data-wz-pick data-role="publish" checked>/);
  assert.match(h, /<input type="radio" id="wz-o-0-1" name="wz-r-0" value="vercel-publish" data-wz-pick data-role="publish">/);
  assert.match(h, /<input type="radio" id="wz-o-0-none" name="wz-r-0" value="" data-wz-pick data-role="publish">/);
  assert.match(h, /<input type="radio" id="wz-o-1-none" name="wz-r-1" value="" data-wz-pick data-role="tokens" checked>/);
  assert.match(h, /типово/);
  assert.match(h, /замість «Публікація в теку»/, "Vercel замінить поточного постачальника");
  assert.match(h, /data-wz="back"/);
  assert.match(h, /data-wz="close"/);
});

test("крок 2: тексти — лід ролі, опис вбудованого модуля, наслідок «Без модуля»; чужий модуль без опису", () => {
  const list = [...LIST, M("custom", ["publish"], { name: "Мій <модуль>" })];
  const h = wizardHTML(V({ step: 2, s2: { list, failed: null, capsError: false, pick: new Set(["static-publish"]), path: "/p" } }));
  assert.match(h, /<p class="cn-sec-lead">Куди канвас викладає превʼю задачі\.<\/p>/);
  assert.match(h, /<span class="wz-opt-desc">Збирає превʼю в теку на цьому компʼютері\./);
  assert.match(h, /<span class="wz-opt-desc">кнопки публікації в смузі нема<\/span>/);
  assert.match(h, /<b>Мій &lt;модуль&gt;<\/b>/, "чужий модуль — `name` маніфесту, екранований");
  assert.equal((h.match(/class="wz-opt-desc"/g) ?? []).length, 3 + 2, "вбудовані static, vercel, css (чужий — без опису) + «Без модуля» у двох секціях");
});

test("довгий текст помилки в деталі обрізається до DETAIL_MAX (300): ні кроку 2, ні кроку 3", () => {
  const long = "x".repeat(500);
  const a = wizardHTML(V({ step: 2, s2: { list: null, failed: { code: "x", message: long }, capsError: false, pick: new Set(), path: "" } }));
  const b = wizardHTML(V({ step: 3, s3: { cards: [], offs: [], failed: { code: "x", message: long }, loading: false } }));
  for (const h of [a, b]) {
    assert.match(h, /x{300}</);
    assert.doesNotMatch(h, /x{301}/);
  }
});

test("крок 2: «замість» — лише в ще не ввімкнених; наслідок «Без модуля» береться з ролі; помилка модуля — причина під описом", () => {
  const list = [
    M("static-publish", ["publish"], { enabled: true, implicit: true, status: "ok" }),
    M("vercel-publish", ["publish"], { enabled: true, status: "error", error: "no-token", last_check: { ok: false, error: "no-token" } }),
  ];
  const h = wizardHTML(V({ step: 2, s2: { list, failed: null, capsError: false, pick: new Set(["static-publish"]), path: "/p" } }));
  assert.doesNotMatch(h, /замість/, "обидва вже ввімкнені — заміни нема");
  assert.match(h, /кнопки публікації в смузі нема/, "наслідок «Без модуля» з ролі");
  assert.match(h, /wz-opt-why[\s\S]*Токен Vercel не задано\./, "причина зламаного постачальника видна, радіо не вимкнене");
  const withDetail = list.map((e) => (e.id === "vercel-publish" ? { ...e, last_check: { ok: false, error: "no-token", detail: "<i>d</i>" } } : e));
  const h2 = wizardHTML(V({ step: 2, s2: { list: withDetail, failed: null, capsError: false, pick: new Set(["static-publish"]), path: "/p" } }));
  assert.match(h2, /Токен Vercel не задано\.<span class="cn-why-detail">&lt;i&gt;d&lt;\/i&gt;<\/span>/, "деталь причини — екранована");
  assert.doesNotMatch(h, /<input type="radio"[^>]* disabled/);
});

test("крок 2: радіо — це відображення pick: без вибору в ролі лишається «Без модуля», вибраний модуль іншої ролі — у своїй", () => {
  const h = wizardHTML(V({ step: 2, s2: { list: LIST, failed: null, capsError: false, pick: new Set(["css-tokens", "vercel-publish"]), path: "/p" } }));
  assert.match(h, /id="wz-o-0-1" name="wz-r-0" value="vercel-publish" data-wz-pick data-role="publish" checked>/);
  assert.doesNotMatch(h, /id="wz-o-0-0"[^>]*checked/);
  assert.doesNotMatch(h, /id="wz-o-0-none"[^>]*checked/);
  assert.match(h, /id="wz-o-1-0" name="wz-r-1" value="css-tokens" data-wz-pick data-role="tokens" checked>/);
  assert.doesNotMatch(h, /id="wz-o-1-none"[^>]*checked/);
});

test("крок 2: модуль із двома ролями стоїть у секції кожної з них, а missing не показується", () => {
  const list = [M("both", ["publish", "tokens"]), M("gone", ["publish"], { status: "missing" })];
  const h = wizardHTML(V({ step: 2, s2: { list, failed: null, capsError: false, pick: new Set(["both"]), path: "/p" } }));
  assert.equal((h.match(/value="both"/g) ?? []).length, 2);
  assert.doesNotMatch(h, /value="gone"/);
  assert.equal((h.match(/value="both"[^>]*checked/g) ?? []).length, 2, "позначений у кожній своїй секції");
});

test("крок 2: вантажиться — «Далі» вимкнена; не прочиталось — помилка з «Спробувати ще», «Далі» доступна", () => {
  assert.match(wizardHTML(V({ step: 2, s2: { list: null, failed: null, capsError: false, pick: new Set(), path: "" } })),
    /data-a="ok" disabled>/);
  const h = wizardHTML(V({ step: 2, s2: { list: null, failed: { code: "x", message: "boom <b>" }, capsError: false, pick: new Set(), path: "" } }));
  assert.match(h, /data-wz="retry"/);
  assert.match(h, /boom &lt;b&gt;/);
  assert.match(h, /data-a="ok">Далі/);
});

test("крок 2: space.json не читається — причина з шляхом, без вибору, «Далі» доступна", () => {
  const h = wizardHTML(V({ step: 2, s2: { list: null, failed: null, capsError: true, pick: new Set(), path: "/u/<x>" } }));
  assert.match(h, /space\.json цього простору не читається — виправте чи видаліть його в \/u\/&lt;x&gt;/);
  assert.doesNotMatch(h, /type="radio"/);
  assert.doesNotMatch(h, /data-wz="retry"/);
  assert.match(h, /data-a="ok">Далі/);
});

test("крок 2 зайнятий: радіо й кнопки вимкнені", () => {
  const h = wizardHTML(V({ step: 2, busy: "save" }));
  assert.ok((h.match(/data-wz-pick[^>]* disabled>/g) ?? []).length >= 4);
  assert.match(h, /data-a="ok" disabled>Далі/);
  assert.match(h, /data-wz="back" disabled/);
  assert.match(h, /data-wz="close" disabled/);
});

test("крок 3: картка з полями (id з префіксом картки), бейдж «Буде підключено», рядок «Без модуля», секрет порожній", () => {
  const vercel = M("vercel-publish", ["publish"], { settings: [{ key: "token", type: "secret", label: "T", set: true }] });
  const card = { entry: vercel, fields: [{ key: "token", type: "secret", label: "T", required: false, set: true }],
    values: {}, erase: [], errors: {}, result: null };
  const h = wizardHTML(V({ step: 3, s3: { cards: [card], offs: [{ role: "tokens", holder: M("css-tokens", ["tokens"], { enabled: true }), result: null }], failed: null, loading: false } }));
  assert.match(h, /<section class="cn-card wz-card" data-id="vercel-publish"/);
  assert.match(h, /id="wz-f-0-0"/);
  assert.match(h, /Буде підключено/);
  assert.match(h, /<li class="wz-off" data-id="css-tokens">/);
  assert.match(h, /вимкнеться — інспектор звіряє без токенів простору\./);
  assert.match(h, /type="password" id="wz-f-0-0"(?![^>]*value=)/);
  assert.match(h, /data-a="ok">Зберегти й далі/);
});

test("крок 3: уже ввімкнений модуль — бейдж стану як у 3a, а не «Буде підключено»; кожна картка — свій префікс id полів", () => {
  const on = M("static-publish", ["publish"], { enabled: true, status: "ok" });
  const off = M("css-tokens", ["tokens"]);
  const cards = [
    { entry: on, fields: [], values: {}, erase: [], errors: {}, result: null },
    { entry: off, fields: [{ key: "file", type: "path", label: "x", required: true }], values: { file: "/a.css" }, erase: [], errors: {}, result: null },
  ];
  const h = wizardHTML(V({ step: 3, s3: { cards, offs: [], failed: null, loading: false } }));
  assert.match(h, /cn-badge cn-badge--ok[^>]*>[\s\S]*?Підключено/);
  assert.equal((h.match(/Буде підключено/g) ?? []).length, 1);
  assert.match(h, /<p class="cn-card-desc">Збирає превʼю в теку на цьому компʼютері\./, "опис вбудованого модуля — і в картці");
  assert.match(h, /<span class="cn-card-role">Публікація<\/span>/);
  assert.match(h, /id="wz-f-1-0"[^>]*value="\/a\.css"/);
  assert.doesNotMatch(h, /id="wz-f-0-/);
});

test("крок 3: помилка поля й результат запису малюються в картці; результат — у слоті data-wz-res", () => {
  const e = M("css-tokens", ["tokens"]);
  const card = { entry: e, fields: [{ key: "file", type: "path", label: "x", required: true }], values: {}, erase: [],
    errors: { file: "cnFieldRequired" }, result: { kind: "failed", key: "cnErrBadFolder", detail: "<i>d</i>" } };
  const h = wizardHTML(V({ step: 3, s3: { cards: [card], offs: [], failed: null, loading: false } }));
  assert.match(h, /id="wz-f-0-0-err">Обовʼязкове поле\./);
  assert.match(h, /aria-invalid="true"/);
  assert.match(h, /<div class="wz-res" data-wz-res="css-tokens"><div class="cn-res cn-res--err" role="alert">/);
  assert.match(h, /Збережено, але перевірка не пройшла\./);
  assert.match(h, /Тека не годиться для превʼю\./);
  assert.match(h, /&lt;i&gt;d&lt;\/i&gt;/);
  assert.doesNotMatch(h, /<i>/);
});

test("крок 3: рядки «Без модуля» — результат вимкнення (успіх, відмова, «заміну не записано»), роль без наслідку — простий рядок", () => {
  const holder = M("css-tokens", ["tokens"], { enabled: true });
  const row = (result, role = "tokens") => ({ role, holder, result });
  const page = (offs) => wizardHTML(V({ step: 3, s3: { cards: [], offs, failed: null, loading: false } }));
  const ok = page([row({ kind: "ok", key: "wzOffDone", detail: "" })]);
  assert.match(ok, /<li class="wz-off" data-id="css-tokens">[\s\S]*cn-res cn-res--ok[\s\S]*Вимкнено\./);
  assert.doesNotMatch(ok, /Нічого не підключаємо/, "рядок вимкнення є — це не «нічого»");
  const blocked = page([row({ kind: "refused", key: "wzOffBlocked", detail: "" })]);
  assert.match(blocked, /cn-res cn-res--err[\s\S]*Не вимкнено: заміну не записано — спершу виправте картку модуля, що його замінює\./);
  /* Роль без своїх текстів (чужа): рядок без наслідку, назва ролі — як є, екранована. */
  const plain = page([row(null, "<b>x</b>")]);
  assert.match(plain, /&lt;b&gt;x&lt;\/b&gt;: «Токени з CSS» вимкнеться\./);
  assert.doesNotMatch(plain, /<b>x/);
  assert.doesNotMatch(plain, /cn-res/, "без результату — без блока результату");
});

test("крок 3: не читається — помилка (текст сервера екранований); вантажиться — «Зберегти й далі» вимкнена", () => {
  const bad = wizardHTML(V({ step: 3, s3: { cards: [], offs: [], failed: { code: "x", message: "<u>m</u>" }, loading: false } }));
  assert.match(bad, /Не вдалося прочитати модулі простору\.[\s\S]*&lt;u&gt;m&lt;\/u&gt;/);
  assert.doesNotMatch(bad, /<u>/);
  assert.doesNotMatch(bad, /Нічого не підключаємо/);
  const load = wizardHTML(V({ step: 3, s3: { cards: [], offs: [], failed: null, loading: true } }));
  assert.match(load, /Завантажую модулі…/);
  assert.match(load, /data-a="ok" disabled>Зберегти й далі/);
});

test("крок 3: нічого — текст «і це нормально»; зайнятий — fieldset вимкнено", () => {
  assert.match(wizardHTML(V({ step: 3 })), /Нічого не підключаємо — і це нормально\./);
  const card = { entry: M("css-tokens", ["tokens"]), fields: [], values: {}, erase: [], errors: {}, result: { kind: "ok", key: "cnCheckOk", detail: "" } };
  const h = wizardHTML(V({ step: 3, busy: "save", s3: { cards: [card], offs: [], failed: null, loading: false } }));
  assert.match(h, /<fieldset class="wz-cards" disabled>/);
  assert.match(h, /cn-res cn-res--ok/);
  assert.match(h, /data-a="ok" disabled>Зберігаю…/);
  assert.match(h, /data-wz="back" disabled/);
  const withField = { ...card, fields: [{ key: "file", type: "path", label: "x", required: false }] };
  const hf = wizardHTML(V({ step: 3, busy: "save", s3: { cards: [withField], offs: [], failed: null, loading: false } }));
  assert.match(hf, /id="wz-f-0-0"[^>]*disabled/, "поле й само вимкнене (не лише через fieldset): так його бачить і `setBusy`, і читач екрана");
  assert.doesNotMatch(wizardHTML(V({ step: 3, s3: { cards: [withField], offs: [], failed: null, loading: false } })), /id="wz-f-0-0"[^>]*disabled/);
  assert.doesNotMatch(wizardHTML(V({ step: 3, s3: { cards: [card], offs: [], failed: null, loading: false } })), /<fieldset class="wz-cards" disabled>/);
});

test("крок 4: поля задачі, радіо «Звідки макет», поле теки сховане до вибору, агент із фразою, «Пропустити»", () => {
  const h = wizardHTML(V({ step: 4 }));
  assert.match(h, /<form class="wz-form wz-task" data-wz-step="4" data-form="task" novalidate>/);
  assert.match(h, /id="tf-title" name="title"/);
  assert.match(h, /id="tf-id" name="id"/);
  const filled = wizardHTML(V({ step: 4, s4: { title: "Екран <b>", id: "ekran", source: "empty", from: "", spaceName: "X", tasks: 0 } }));
  assert.match(filled, /id="tf-title" name="title" type="text" value="Екран &lt;b&gt;"/);
  assert.match(filled, /id="tf-id" name="id" type="text" value="ekran"/);
  assert.match(h, /<input type="radio" name="wz-src" value="empty" checked>/);
  assert.match(h, /<div class="cn-field" id="wz-from-f" hidden>/);
  assert.match(h, /<code class="cn-code" id="wz-phrase">створи задачу «екран оплати» у просторі «Клієнт»<\/code>/);
  assert.match(h, /data-wz="copy"/);
  assert.match(h, /data-wz="skip"[^>]*>Пропустити/);
  const f = wizardHTML(V({ step: 4, s4: { title: "", id: "", source: "folder", from: "~/m", spaceName: "X", tasks: 3 } }));
  assert.match(f, /<div class="cn-field" id="wz-from-f">/);
  assert.match(f, /value="~\/m"/);
  assert.match(f, /Задач у просторі вже: 3/);
  assert.match(f, /data-wz="skip"[^>]*>До задач/);
});

test("крок 4: радіо джерела — рівно одне вибране; «Створити й відкрити» — submit; зайнятий — усе вимкнено", () => {
  const empty = wizardHTML(V({ step: 4 }));
  assert.doesNotMatch(empty, /value="folder" checked/);
  const folder = wizardHTML(V({ step: 4, s4: { title: "", id: "", source: "folder", from: "", spaceName: "X", tasks: 0 } }));
  assert.match(folder, /<input type="radio" name="wz-src" value="folder" checked>/);
  assert.doesNotMatch(folder, /value="empty" checked/);
  assert.match(empty, /<button type="submit" class="ctl ctl--pri" data-a="ok">Створити й відкрити<\/button>/);
  assert.match(empty, /Задача — одна фіча чи екран/, "без задач — звичайний лід");
  const busy = wizardHTML(V({ step: 4, busy: "save" }));
  assert.match(busy, /data-form="task" novalidate aria-busy="true">/);
  assert.match(busy, /data-a="ok" disabled>Створюю…/);
  assert.match(busy, /data-wz="back" disabled/);
  assert.match(busy, /data-wz="skip" disabled|data-wz="skip"[^>]* disabled/);
  assert.match(busy, /id="tf-title"[^>]*disabled/);
  assert.match(busy, /id="wz-from"[^>]*disabled/);
  assert.match(busy, /name="wz-src" value="empty" checked disabled/);
});

test("крок 4: зворотного кроку нема лише на кроці 1; слот помилки #wz-err — на кроках 1 і 4", () => {
  for (const [step, back, err] of [[1, false, true], [2, true, false], [3, true, false], [4, true, true]]) {
    const h = wizardHTML(V({ step }));
    assert.equal(/data-wz="back"/.test(h), back, `back, крок ${step}`);
    assert.equal(/id="wz-err"/.test(h), err, `#wz-err, крок ${step}`);
  }
});

test("усе з даних екранується", () => {
  const evil = "<img src=x onerror=1>";
  const h = [
    wizardHTML(V({ s1: { name: evil, color: "space-1\" onclick=\"x", path: evil, folderFirst: false } })),
    wizardHTML(V({ step: 2, s2: { list: [M(evil, [evil])], failed: null, capsError: false, pick: new Set([evil]), path: "" } })),
    wizardHTML(V({ step: 4, s4: { title: evil, id: evil, source: "folder", from: evil, spaceName: evil, tasks: 0 } })),
  ].join("");
  assert.doesNotMatch(h, /<img/);
  assert.doesNotMatch(h, /onclick="x/);
});

test("екранується й крок 3 (назви модулів і ролей у картках та рядках «Без модуля»)", () => {
  const evil = "<img src=x onerror=1>";
  const e = M(evil, [evil], { name: evil, settings: [{ key: "k", type: "path", label: evil }] });
  const card = { entry: e, fields: [{ key: "k", type: "path", label: evil, required: false }], values: { k: evil }, erase: [], errors: {}, result: null };
  const h = wizardHTML(V({ step: 3, s3: { cards: [card], offs: [{ role: evil, holder: e, result: null }], failed: null, loading: false } }));
  assert.doesNotMatch(h, /<img/);
});

test("англійська: жодної кирилиці в розмітці кожного кроку з латинськими даними", () => {
  const before = getLang();
  setLang("en");
  try {
    for (const step of [1, 2, 3, 4]) {
      const h = wizardHTML(V({ step, s1: { name: "X", color: "space-1", path: "~/x", folderFirst: false }, s4: { title: "", id: "", source: "empty", from: "", spaceName: "X", tasks: 0 } }));
      assert.doesNotMatch(h, CYR, `крок ${step}`);
    }
    /* Станів із додатковими текстами — теж: помилки, рядки вимкнення, зайнятість, редагування, задачі в просторі. */
    const holder = M("css-tokens", ["tokens"], { enabled: true });
    const card = { entry: M("vercel-publish", ["publish"]), fields: [{ key: "token", type: "secret", label: "T", required: true, set: false }],
      values: {}, erase: [], errors: { token: "cnFieldRequired" }, result: { kind: "failed", key: "cnErrNoToken", detail: "" } };
    /* Дані — латиницею: перевіряємо тексти кроку, а не «Клієнт» із типових даних `V`. */
    const L = (o) => V({ s1: { name: "X", color: "space-1", path: "~/x", folderFirst: false },
      s4: { title: "", id: "", source: "empty", from: "", spaceName: "X", tasks: 0 }, ...o });
    const pages = [
      L({ created: true }), L({ busy: "save" }), L({ created: true, busy: "save" }),
      L({ step: 2, s2: { list: null, failed: { code: "x", message: "m" }, capsError: false, pick: new Set(), path: "" } }),
      L({ step: 2, s2: { list: null, failed: null, capsError: true, pick: new Set(), path: "/p" } }),
      L({ step: 2, s2: { list: null, failed: null, capsError: false, pick: new Set(), path: "" } }),
      L({ step: 3, s3: { cards: [card], offs: [{ role: "tokens", holder, result: { kind: "refused", key: "wzOffBlocked", detail: "" } },
        { role: "comments", holder, result: { kind: "ok", key: "wzOffDone", detail: "" } }], failed: null, loading: false } }),
      L({ step: 3, busy: "save" }), L({ step: 3, s3: { cards: [], offs: [], failed: { code: "x", message: "m" }, loading: false } }),
      L({ step: 4, s4: { title: "", id: "", source: "folder", from: "~/m", spaceName: "X", tasks: 2 } }), L({ step: 4, busy: "save" }),
    ];
    pages.forEach((p, i) => assert.doesNotMatch(wizardHTML(p), CYR, `стан ${i}`));
  } finally { setLang(before); }
});

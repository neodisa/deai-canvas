import assert from "node:assert/strict";
import test from "node:test";
import { DICT, getLang, setLang } from "../app/i18n.js";
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
  assert.match(h, /<fieldset class="wz-sec" aria-describedby="wz-sl-0"><legend class="cn-sec-h">Публікація<\/legend>/);
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
  assert.match(h, /<p class="cn-sec-lead" id="wz-sl-0">Куди канвас викладає превʼю задачі\.<\/p>/);
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
  assert.match(h, /<li class="wz-off" data-id="css-tokens" tabindex="-1">/);
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
  assert.match(ok, /<li class="wz-off" data-id="css-tokens" tabindex="-1">[\s\S]*cn-res cn-res--ok[\s\S]*Вимкнено\./);
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
  /* Не глухий кут: «Спробувати ще» є, а «Зберегти й далі» вимкнена — писати нема що (список не прочитався). */
  assert.match(bad, /data-wz="retry"/);
  assert.match(bad, /data-a="ok" disabled>Зберегти й далі/);
  assert.match(bad, /data-wz="back">/, "«Назад» і «Закрити майстер» доступні");
  assert.match(bad, /data-wz="close">/);
  assert.doesNotMatch(wizardHTML(V({ step: 3 })), /data-wz="retry"/, "без помилки «Спробувати ще» нема");
  assert.doesNotMatch(wizardHTML(V({ step: 3 })), /data-a="ok" disabled/);
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

test("екранування: імена тримачів у «замість «X»» (крок 2) і шлях у режимі правки (крок 1)", () => {
  const evil = "<img src=x onerror=alert(1)>";
  const list = [M("holder", ["publish"], { name: evil, enabled: true }), M("vercel-publish", ["publish"])];
  const h = wizardHTML(V({ step: 2, s2: { list, failed: null, capsError: false, pick: new Set(["holder"]), path: "/p" } }));
  assert.match(h, /замість «&lt;img src=x onerror=alert\(1\)&gt;»/, "імʼя тримача — екрановане в підписі «замість»");
  assert.doesNotMatch(h, /<img/);
  const e = wizardHTML(V({ created: true, s1: { name: evil, color: "space-1", path: evil, folderFirst: false } }));
  assert.match(e, /id="sp-path" name="path" type="text" value="&lt;img src=x onerror=alert\(1\)&gt;" readonly/);
  assert.doesNotMatch(e, /<img/);
});

/* ── усі стани сторінки: один перелік для перевірок зв'язків і мов ─────────────────────────────────── */

const LATIN = { s1: { name: "X", color: "space-1", path: "~/x", folderFirst: false },
  s4: { title: "", id: "", source: "empty", from: "", spaceName: "X", tasks: 0 } };
const S2 = (o) => ({ list: LIST, failed: null, capsError: false, pick: new Set(["static-publish"]), path: "/p", ...o });
const S3 = (o) => ({ cards: [], offs: [], failed: null, loading: false, ...o });

/** Усі стани розмітки. `mk` — конструктор вʼю з даними потрібної мови (`V` — кирилиця в типових даних, `L` — латиниця). */
function allStates(mk) {
  const holder = M("css-tokens", ["tokens"], { enabled: true });
  const rich = [
    { entry: M("vercel-publish", ["publish"], { enabled: true, status: "error", error: "no-token", last_check: { ok: false, error: "no-token", detail: "d" } }),
      fields: [{ key: "token", type: "secret", label: "T", required: false, set: true }, { key: "team", type: "text", label: "t", required: true },
        { key: "dir", type: "path", label: "p" }, { key: "on", type: "bool", label: "b" },
        { key: "mode", type: "select", label: "m", options: [{ value: "a", label: "A" }], blank: true }],
      values: {}, erase: ["token"], errors: { team: "cnFieldRequired", token: "cnFieldRequired" }, result: { kind: "failed", key: "cnErrNoToken", detail: "x" } },
    { entry: M("css-tokens", ["tokens"]), fields: [{ key: "file", type: "path", label: "f", required: true, set: false }, { key: "key", type: "secret", label: "K", required: true, set: false }],
      values: { file: "/a.css" }, erase: [], errors: {}, result: null },
    { entry: M("static-publish", ["publish"], { enabled: true, status: "ok" }), fields: [], values: {}, erase: [], errors: {}, result: { kind: "ok", key: "cnCheckOk", detail: "" } },
  ];
  const lists = [
    LIST,
    [M("both", ["publish", "tokens"]), M("x", ["weird"]), M("e", ["publish"], { enabled: true, status: "error", error: "no-token" })],
  ];
  return [
    mk({ step: 1 }), mk({ step: 1, created: true }), mk({ step: 1, busy: "save" }), mk({ step: 1, created: true, busy: "save" }),
    mk({ step: 2 }), mk({ step: 2, busy: "save" }),
    ...lists.map((list) => mk({ step: 2, s2: S2({ list, pick: new Set(["both"]) }) })),
    mk({ step: 2, s2: S2({ list: null }) }),
    mk({ step: 2, s2: S2({ list: null, failed: { code: "x", message: "m" } }) }),
    mk({ step: 2, s2: S2({ list: null, capsError: true }) }),
    mk({ step: 3 }), mk({ step: 3, busy: "save" }),
    mk({ step: 3, s3: S3({ cards: rich, offs: [{ role: "tokens", holder, result: { kind: "refused", key: "wzOffBlocked", detail: "" } },
      { role: "comments", holder, result: { kind: "ok", key: "wzOffDone", detail: "" } }, { role: "tokens", holder, result: null }] }) }),
    mk({ step: 3, busy: "save", s3: S3({ cards: rich }) }),
    mk({ step: 3, s3: S3({ loading: true }) }),
    mk({ step: 3, s3: S3({ failed: { code: "x", message: "m" } }) }),
    mk({ step: 4 }), mk({ step: 4, busy: "save" }),
    mk({ step: 4, s4: { title: "T", id: "t", source: "folder", from: "~/m", spaceName: "X", tasks: 2 } }),
  ];
}
const L = (o) => V({ ...LATIN, ...o });

/** Кожне посилання (`aria-describedby`, `aria-labelledby`, `label[for]`) веде рівно на один id; id не дублюються. */
function assertRefs(h, label) {
  const count = new Map();
  for (const m of h.matchAll(/\sid="([^"]+)"/g)) count.set(m[1], (count.get(m[1]) ?? 0) + 1);
  for (const [id, n] of count) assert.equal(n, 1, `${label}: id «${id}» повторюється ${n} рази`);
  const refs = [];
  for (const m of h.matchAll(/\saria-(?:describedby|labelledby)="([^"]*)"/g)) refs.push(...m[1].split(/\s+/).filter(Boolean));
  for (const m of h.matchAll(/<label\b[^>]*\sfor="([^"]+)"/g)) refs.push(m[1]);
  for (const r of refs) assert.equal(count.get(r), 1, `${label}: посилання на «${r}» не веде на один id`);
  return refs.length;
}

test("зв'язки доступності в усіх станах (UK і EN): кожне посилання веде рівно на один id, id не дублюються", () => {
  const before = getLang();
  try {
    for (const lang of ["uk", "en"]) {
      setLang(lang);
      const states = allStates(lang === "uk" ? V : L);
      assert.ok(states.length >= 20);
      let refs = 0;
      states.forEach((v, i) => { refs += assertRefs(wizardHTML(v), `${lang} стан ${i} (крок ${v.step})`); });
      assert.ok(refs > 100, "перевірка не порожня");
    }
  } finally { setLang(before); }
});

test("перевірка зв'язків справді ловить: висяче посилання й дубль id", () => {
  assert.throws(() => assertRefs('<input id="a" aria-describedby="a b">', "x"), /«b»/);
  assert.throws(() => assertRefs('<i id="a"></i><b id="a"></b>', "x"), /повторюється/);
  assert.throws(() => assertRefs('<label for="q">x</label>', "x"), /«q»/);
  assert.equal(assertRefs('<label for="q">x</label><input id="q" aria-labelledby="q">', "x"), 2);
});

test("англійська: жодної кирилиці в розмітці кожного кроку з латинськими даними — у всіх станах", () => {
  const before = getLang();
  setLang("en");
  try {
    allStates(L).forEach((v, i) => assert.doesNotMatch(wizardHTML(v), CYR, `стан ${i} (крок ${v.step})`));
  } finally { setLang(before); }
});

/* ── точкові пінни доступності ─────────────────────────────────────────────────────────────────────── */

test("кружки кольору: у кожному — галочка (не лише колір показує вибір); картки й секції названі через aria-labelledby", () => {
  const h = wizardHTML(V());
  const sw = [...h.matchAll(/<button type="button" class="cv-color" role="radio"[\s\S]*?<\/button>/g)].map((m) => m[0]);
  assert.equal(sw.length, 6);
  for (const b of sw) assert.match(b, /<use href="#i-check"\/>/);
  assert.match(h, /<div class="cv-colors wz-colors" role="radiogroup" aria-labelledby="sp-color-l">/);
  assert.match(h, /<span class="cn-lbl" id="sp-color-l">Колір<\/span>/);
  const card = { entry: M("css-tokens", ["tokens"]), fields: [], values: {}, erase: [], errors: {}, result: null };
  const c = wizardHTML(V({ step: 3, s3: S3({ cards: [card, { ...card, entry: M("vercel-publish", ["publish"]) }] }) }));
  assert.match(c, /<section class="cn-card wz-card" data-id="css-tokens"[^>]* aria-labelledby="wz-c-0"/);
  assert.match(c, /<b id="wz-c-0">Токени з CSS<\/b>/);
  assert.match(c, /<section class="cn-card wz-card" data-id="vercel-publish"[^>]* aria-labelledby="wz-c-1"/);
  assert.match(c, /<b id="wz-c-1">Vercel<\/b>/);
});

test("поля, що описують себе підказками: #sp-path (нове й правка) і #wz-from, #sp-name, #tf-title, #tf-id", () => {
  const n = wizardHTML(V());
  assert.match(n, /id="sp-path"[^>]*aria-describedby="sp-found sp-registered wz-s1-hint wz-err"/);
  assert.match(n, /id="sp-name"[^>]*aria-describedby="wz-err"/);
  const e = wizardHTML(V({ created: true }));
  assert.match(e, /id="sp-path"[^>]*readonly aria-describedby="wz-s1-hint"/);
  const t4 = wizardHTML(V({ step: 4 }));
  assert.match(t4, /id="wz-from"[^>]*aria-describedby="wz-from-hint wz-err"/);
  assert.match(t4, /id="tf-title"[^>]*aria-describedby="wz-demo-why wz-err"/);
  assert.match(t4, /id="tf-id"[^>]*aria-describedby="wz-demo-why wz-err"/);
  assert.match(t4, /<p class="cn-hint" id="wz-from-hint">/);
});

test("крок 2: лід секції привʼязаний до її fieldset через aria-describedby (id унікальні); без ліду — без атрибута", () => {
  const h = wizardHTML(V({ step: 2 }));
  assert.match(h, /<fieldset class="wz-sec" aria-describedby="wz-sl-0"><legend class="cn-sec-h">Публікація<\/legend><p class="cn-sec-lead" id="wz-sl-0">/);
  assert.match(h, /<fieldset class="wz-sec" aria-describedby="wz-sl-1"><legend class="cn-sec-h">Токени дизайн-системи<\/legend><p class="cn-sec-lead" id="wz-sl-1">/);
  /* Чужа роль без своїх текстів: ліду нема — і describedby нема (висяче посилання було б вадою). */
  const odd = wizardHTML(V({ step: 2, s2: S2({ list: [M("x", ["weird"])], pick: new Set() }) }));
  assert.match(odd, /<fieldset class="wz-sec"><legend class="cn-sec-h">weird<\/legend>/);
  assert.doesNotMatch(odd, /wz-sl-/);
});

test("роль notify (4c-3) у майстрі: секція зі своїм заголовком, лідом і текстом «Без модуля»; рядок вимкнення й підписи полів — зі словника", () => {
  const st = M("supabase-teams", ["notify"], { settings: [{ key: "url", type: "text" }, { key: "key", type: "secret" }] });
  const h = wizardHTML(V({ step: 2, s2: S2({ list: [st], pick: new Set() }) }));
  assert.match(h, /<legend class="cn-sec-h">Сповіщення Teams<\/legend><p class="cn-sec-lead" id="wz-sl-0">Картка в канал Teams на кожен новий коментар; тиша — на канал задачі\.<\/p>/);
  assert.match(h, /<span class="wz-opt-desc">Без сповіщень — Teams мовчить\.<\/span>/, "«Без модуля» несе текст ролі");
  assert.match(h, /Supabase — Teams/, "назва вбудованого модуля — зі словника, не сирий id");
  const holder = M("supabase-teams", ["notify"], { enabled: true });
  const o = wizardHTML(V({ step: 3, s3: S3({ offs: [{ role: "notify", holder, result: null }] }) }));
  assert.match(o, /Сповіщення Teams: «Supabase — Teams» вимкнеться — Без сповіщень — Teams мовчить\./);
  const f = wizardHTML(V({ step: 3, s3: S3({ cards: [{ entry: st, fields: [], values: {}, erase: [], errors: {},
    result: { kind: "failed", key: "cnErrNotifyNoWebhook", detail: "x" } }] }) }));
  assert.match(f, /У Vault нема секрету teams_webhook_url/, "перевірка модуля notify пояснена власним кодом");
  const before = getLang();
  try {
    setLang("en");
    const e = wizardHTML(V({ step: 2, s2: S2({ list: [st], pick: new Set() }) }));
    assert.match(e, /<legend class="cn-sec-h">Teams notifications<\/legend>/);
    assert.match(e, /No notifications — Teams stays silent\./);
  } finally { setLang(before); }
});

test("контейнери картки й рядка «Без модуля» фокусовні програмно (tabindex=-1): контролер веде фокус на збій без контролів", () => {
  const e = M("css-tokens", ["tokens"]);
  const h = wizardHTML(V({ step: 3, s3: S3({ cards: [{ entry: e, fields: [], values: {}, erase: [], errors: {}, result: null }],
    offs: [{ role: "tokens", holder: M("x", ["tokens"], { enabled: true }), result: null }] }) }));
  assert.match(h, /<section class="cn-card wz-card" data-id="css-tokens" tabindex="-1" aria-labelledby="wz-c-0">/);
  assert.match(h, /<li class="wz-off" data-id="x" tabindex="-1">/);
});

test("крок 3: ввімкнений модуль із помилкою показує причину, як картка 3a (cn-why); решта станів — без неї", () => {
  const card = (extra) => ({ entry: M("vercel-publish", ["publish"], extra), fields: [], values: {}, erase: [], errors: {}, result: null });
  const page = (extra) => wizardHTML(V({ step: 3, s3: S3({ cards: [card(extra)] }) }));
  const bad = page({ enabled: true, status: "error", error: "no-token", last_check: { ok: false, error: "no-token", detail: "<i>d</i>" } });
  assert.match(bad, /<div class="cn-why"><svg[^>]*><use href="#i-warn"\/><\/svg><span>Токен Vercel не задано\.<span class="cn-why-detail">&lt;i&gt;d&lt;\/i&gt;<\/span><\/span><\/div>/);
  assert.match(bad, /cn-badge cn-badge--error/);
  assert.doesNotMatch(bad, /<i>/);
  assert.doesNotMatch(page({ enabled: true, status: "ok" }), /cn-why/);
  assert.doesNotMatch(page({ enabled: true, status: "unchecked" }), /cn-why/);
  assert.doesNotMatch(page({ enabled: false, status: "error", error: "no-token" }), /cn-why/, "ще не ввімкнений — «Буде підключено», без причини");
});

test("крок 3: збій перевірки після запису — одне повідомлення в картці (результат `failed`), а не причина над полями ще й під ними", () => {
  const bad = M("vercel-publish", ["publish"], { enabled: true, status: "error", error: "no-token",
    last_check: { ok: false, error: "no-token", detail: "d" } });
  const page = (result) => wizardHTML(V({ step: 3, s3: S3({ cards: [{ entry: bad, fields: [], values: {}, erase: [], errors: {}, result }] }) }));
  const count = (h, re) => (h.match(re) || []).length;
  const TEXT = /Токен Vercel не задано\./g;
  /* Результат запису `failed` (відповідь `module-enable` вже поклала в запис статус error): лише він, без `cn-why` над полями. */
  const failed = page({ kind: "failed", key: "cnErrNoToken", detail: "d" });
  assert.doesNotMatch(failed, /cn-why"/, "причина над полями не малюється, коли є результат failed");
  assert.equal(count(failed, TEXT), 1, "текст відмови — рівно один раз");
  assert.equal(count(failed, /Збережено, але перевірка не пройшла\./g), 1);
  assert.match(failed, /cn-badge cn-badge--error/, "бейдж стану лишається");
  /* Без результату (картка щойно відкрита, модуль уже зламаний) — причина, як у картці 3a. */
  const none = page(null);
  assert.equal(count(none, /<div class="cn-why">/g), 1);
  assert.equal(count(none, TEXT), 1);
  assert.doesNotMatch(none, /Збережено, але перевірка не пройшла/);
  /* Не `failed` — не повтор: відмова HTTP («не збережено») каже про запис, а причина — про поточний стан модуля. */
  const refused = page({ kind: "refused", key: "cnRefBadSettings", detail: "" });
  assert.equal(count(refused, /<div class="cn-why">/g), 1, "відмова не прибирає причину");
  assert.match(refused, /cn-res cn-res--err/);
});

test("data-step — число: рядок із пробілами нормалізується; крок вибирається за числом", () => {
  const h = wizardHTML(V({ step: " 3 " }));
  assert.match(h, /<div class="th-in wz" data-step="3">/);
  assert.match(h, /data-wz-step="3"/);
  assert.match(h, /wz-step--cur" aria-current="step"><span class="wz-step-bar" aria-hidden="true"><\/span><span class="wz-step-name">Налаштування/);
});

test("словник: тексти за спекою — «Простір більше недоступний», запитання про відкидання налаштувань", () => {
  assert.equal(DICT.uk.wzSpaceGone, "Простір більше недоступний.");
  assert.equal(DICT.en.wzSpaceGone, "The space is no longer available.");
  assert.equal(DICT.uk.wzDiscardAsk, "Відкинути незбережені налаштування?");
  assert.equal(DICT.en.wzDiscardAsk, "Discard unsaved settings?");
});

test("крок 4: третій варіант «Демо-задача (Tally)»; вибраний — назва й id вимкнені, причина поруч", () => {
  const empty = wizardHTML(V({ step: 4 }));
  assert.match(empty, /<input type="radio" name="wz-src" value="demo"> Демо-задача \(Tally\)<\/label>/);
  assert.match(empty, /<p class="cn-hint" id="wz-demo-why" hidden>/);
  assert.doesNotMatch(empty, /id="tf-title"[^>]*disabled/);
  const demo = wizardHTML(V({ step: 4, s4: { title: "", id: "", source: "demo", from: "", spaceName: "X", tasks: 0 } }));
  assert.match(demo, /value="demo" checked>/);
  assert.match(demo, /id="tf-title"[^>]*aria-describedby="wz-demo-why wz-err" disabled>/);
  assert.match(demo, /id="tf-id"[^>]*aria-describedby="wz-demo-why wz-err" disabled>/);
  assert.match(demo, /<p class="cn-hint" id="wz-demo-why">Назву й ідентифікатор демо-задачі канвас дасть сам\.<\/p>/);
  assert.doesNotMatch(demo, /value="empty" checked/);
});

import assert from "node:assert/strict";
import test from "node:test";

import { commentsPanelHTML } from "../app/comments-view.js";
import { setLang } from "../app/i18n.js";

setLang("uk");
const C = (o) => ({ id: o.id, n: o.n, text: o.text || "т", author: o.author || "Автор А", ts: "13.11.2026 10:00",
  status: o.status || "open", scope: o.scope || "current", where: o.where || "here", iter: o.iter || "3",
  resolvedV: o.resolvedV ?? null, resolveReason: o.resolveReason ?? null, meta: o.meta || {} });
const base = (over = {}) => ({ snapshot: { version: "3", iteration: "3", comments: [] }, query: "", selectedId: null,
  editingId: null, expanded: { earlier: false, closed: false }, filter: "local", dual: false, teamDown: null, fresh: null, down: null, ...over });

test("порожньо — запрошення; немає знімка — завантаження; є відмова — її текст", () => {
  assert.match(commentsPanelHTML(base()), /Коментарів ще немає/);
  assert.match(commentsPanelHTML(base({ snapshot: null })), /Коментатор завантажується/);
  assert.match(commentsPanelHTML(base({ snapshot: null, down: "адаптер не завантажився" })), /Коментарі недоступні: адаптер не завантажився/);
});

test("тексти людей екрануються, шкідлива мініатюра не малюється", () => {
  const html = commentsPanelHTML(base({ snapshot: { iteration: "3", comments: [
    C({ id: "x", n: 1, text: "<img src=x onerror=alert(1)>", author: "<b>я</b>", meta: { shot: "javascript:alert(1)", sel: "<i>" } }),
  ] } }));
  assert.equal(html.includes("<img src=x"), false);
  assert.equal(html.includes("<b>я</b>"), false);
  assert.equal(html.includes("javascript:"), false);
  assert.match(html, /&lt;img src=x/);
});

test("картка відкритого: номер, автор, дії Показати/Редагувати/Закрити/Видалити; виділена — клас", () => {
  const html = commentsPanelHTML(base({ selectedId: "a", snapshot: { iteration: "3", comments: [C({ id: "a", n: 2 })] } }));
  assert.match(html, /class="cmt-card cmt-card--sel"[^>]*data-cid="a"/);
  for (const act of ["cmtshow", "cmtedit", "cmtres", "cmtdel"]) assert.match(html, new RegExp(`data-act="${act}" data-val="a"`));
  assert.match(html, /<span class="cmt-n">2<\/span>/);
});

test("редагування — textarea з текстом і Зберегти/Скасувати", () => {
  const html = commentsPanelHTML(base({ editingId: "a", snapshot: { iteration: "3", comments: [C({ id: "a", n: 1, text: "було" })] } }));
  assert.match(html, /<textarea class="cmt-edit"[^>]*>було<\/textarea>/);
  assert.match(html, /data-act="cmteditsave" data-val="a"/);
});

test("закрита картка: «Зроблено · Іт.N» і що зробив Claude; без resolvedV — «Закрито»", () => {
  const comments = [C({ id: "d", n: 1, status: "resolved", resolvedV: 2, resolveReason: "Зробив кнопку ширшою" }),
                    C({ id: "e", n: 2, status: "resolved" })];
  const html = commentsPanelHTML(base({ expanded: { earlier: false, closed: true }, snapshot: { iteration: "3", comments } }));
  assert.match(html, /Зроблено · Іт\.2/);
  assert.match(html, /Зробив кнопку ширшою/);
  assert.match(html, /Закрито/);
  assert.match(html, /data-act="cmtreopen" data-val="d"/);
});

test("попередні й закриті згорнуті: заголовок із числом, карток нема до розгортання", () => {
  const comments = [C({ id: "o", n: 1, scope: "earlier", iter: "2" }), C({ id: "z", n: 2, status: "resolved" })];
  const folded = commentsPanelHTML(base({ snapshot: { iteration: "3", comments } }));
  assert.match(folded, /data-act="cmtsec" data-val="earlier" aria-expanded="false"/);
  assert.match(folded, /З попередніх ітерацій \(1\)/);
  assert.equal(folded.includes('data-cid="o"'), false);
  const open = commentsPanelHTML(base({ expanded: { earlier: true, closed: false }, snapshot: { iteration: "3", comments } }));
  assert.match(open, /data-act="cmtcarry" data-val="o"[^>]*>Перенести в Іт\.3/);
  assert.match(open, /Іт\.2/);
});

test("фільтр — окремим рядком під пошуком, порядок Для AI · Команда · Усі, з числами; без dual — нема", () => {
  assert.equal(commentsPanelHTML(base()).includes('data-act="cmtfilter"'), false);
  assert.equal(commentsPanelHTML(base()).includes('class="cmt-filter"'), false);
  assert.equal(commentsPanelHTML(base()).includes('data-act="cmtch"'), false, "перемикача каналу більше нема (поправка 10)");
  const comments = [
    { ...C({ id: "l", n: 1 }), _aud: "local" },
    { ...C({ id: "p", n: 2 }), _aud: "project" },
    { ...C({ id: "a", n: 3, meta: { assignee: "claude" } }), _aud: "project" },
  ];
  const html = commentsPanelHTML(base({ dual: true, filter: "project", fresh: new Set(["p"]), snapshot: { iteration: "3", comments } }));
  const order = [...html.matchAll(/data-act="cmtfilter" data-val="(\w+)"/g)].map((m) => m[1]);
  assert.deepEqual(order, ["local", "project", "all"]);
  assert.match(html, /data-val="local" aria-pressed="false"><span>Для AI<\/span><span class="cmt-fn">2<\/span><\/button>/);
  assert.match(html, /data-val="project" aria-pressed="true"><span>Команда<\/span><span class="cmt-fn">2<\/span><span class="cmt-fnew"[^>]*>\+1<\/span><\/button>/);
  assert.match(html, /data-val="all" aria-pressed="false"><span>Усі<\/span><span class="cmt-fn">3<\/span><\/button>/);
  assert.ok(html.indexOf('id="cmt-q"') < html.indexOf('class="cmt-filter"'), "фільтр — під пошуком, не в шапці");
  // Рядка-пояснення під фільтром нема: власник 16.11.2026 — підписи, про які не просили, загромождають панель.
  assert.equal(html.includes("cmt-fhint"), false);
  assert.match(html, /aria-label="Кому"/);
  assert.equal(html.includes("cmt-total"), false, "з фільтром числа у вкладках, не в шапці");
  assert.equal(commentsPanelHTML(base({ dual: true, filter: "local" })).includes("cmt-fnew"), false, "без нових мітки нема");
});

test("невідоме значення фільтра — вкладка «Для AI»", () => {
  const html = commentsPanelHTML(base({ dual: true, filter: "сміття" }));
  assert.match(html, /data-val="local" aria-pressed="true"/);
});

test("шапка: іконка, назва, кнопки icob; icon-btn більше нема; без dual — число в шапці", () => {
  const html = commentsPanelHTML(base({ snapshot: { iteration: "3", comments: [C({ id: "a", n: 1 })] } }));
  assert.equal(html.includes("icon-btn"), false);
  assert.match(html, /<button type="button" class="icob" data-act="cmtpins"/);
  assert.match(html, /<button type="button" class="icob" data-act="comments"/);
  assert.match(html, /<div class="insp-top cmt-top"><svg[^>]*>.*?<\/svg><span class="panel-title">Коментарі<\/span><span class="cmt-total">1<\/span>/s);
});

test("картка: номер локального — фіолетовий лише з dual; бейдж «Доручено AI»; іконкові дії — cmt-ib", () => {
  const comments = [{ ...C({ id: "l", n: 1 }), _aud: "local" }, { ...C({ id: "a", n: 2, meta: { assignee: "claude" } }), _aud: "project" }];
  const dual = commentsPanelHTML(base({ dual: true, filter: "all", snapshot: { iteration: "3", comments } }));
  assert.match(dual, /<span class="cmt-n cmt-n--local">1<\/span>/);
  assert.match(dual, /<span class="cmt-n">2<\/span>/);
  assert.match(dual, /<span class="cmt-badge">Доручено AI<\/span>/);
  assert.match(dual, /class="cmt-act" data-act="cmtshow"/);
  for (const act of ["cmtedit", "cmtres", "cmtdel"]) assert.match(dual, new RegExp(`class="cmt-ib" data-act="${act}"`));
  const single = commentsPanelHTML(base({ snapshot: { iteration: "3", comments: [C({ id: "l", n: 1 })] } }));
  assert.match(single, /<span class="cmt-n">1<\/span>/, "без командного каналу піни не фіолетові — і номер теж");
});

test("смуга падіння командного: причина екранована; без причини смуги нема", () => {
  const html = commentsPanelHTML(base({ teamDown: "<b>збій</b>" }));
  assert.match(html, /<p class="cmt-teamdown" role="alert">Командні коментарі недоступні: &lt;b&gt;збій&lt;\/b&gt;<\/p>/);
  assert.equal(html.includes("<b>збій"), false);
  assert.equal(commentsPanelHTML(base()).includes("cmt-teamdown"), false);
});

const D = (o) => ({ ...C(o), ...(o.aud ? { _aud: o.aud } : {}) });
const dual = (comments, over = {}) => commentsPanelHTML(base({ dual: true, filter: "all", snapshot: { iteration: "3", comments }, ...over }));

test("адресат і бейдж доручення — лише в dual", () => {
  const cs = [D({ id: "a", n: 1, aud: "project", meta: { assignee: "claude" } }), D({ id: "b", n: 2 })];
  const html = dual(cs);
  assert.match(html, /<span class="cmt-aud cmt-aud--project">Команда<\/span>/);
  assert.match(html, /<span class="cmt-aud cmt-aud--local">AI<\/span>/);
  assert.equal((html.match(/class="cmt-badge"/g) || []).length, 1);
  const single = commentsPanelHTML(base({ snapshot: { iteration: "3", comments: cs } }));
  assert.equal(single.includes("cmt-aud"), false);
  assert.equal(single.includes("cmt-badge"), false);
  assert.equal(single.includes("cmtassign"), false);
});

test("«Доручити» / «Забрати» — лише на відкритих командних; не на локальних і не на закритих", () => {
  const html = dual([D({ id: "a", n: 1, aud: "project" }), D({ id: "b", n: 2, aud: "project", meta: { assignee: "claude" } }),
    D({ id: "c", n: 3 }), D({ id: "z", n: 4, aud: "project", status: "resolved" })], { expanded: { earlier: false, closed: true } });
  assert.match(html, /data-act="cmtassign" data-val="a"[^>]*>Доручити AI</);
  assert.match(html, /data-act="cmtunassign" data-val="b"[^>]*>Забрати в AI</);
  assert.equal(/data-act="cmt(un)?assign" data-val="c"/.test(html), false, "локальний");
  assert.equal(/data-act="cmt(un)?assign" data-val="z"/.test(html), false, "закритий");
  assert.ok(html.indexOf('data-act="cmtassign" data-val="a"') < html.indexOf('data-act="cmtedit" data-val="a"'), "перед «Редагувати»");
});

test("розділ «Нове»: з числом, над «Відкритими», без дубля там", () => {
  const html = dual([D({ id: "n1", n: 5, aud: "project" }), D({ id: "o1", n: 1 })], { fresh: new Set(["n1"]) });
  assert.match(html, /<h3 class="cmt-h cmt-h--new">Нове <span>1<\/span><\/h3>/);
  assert.ok(html.indexOf("cmt-sec--new") < html.indexOf('aria-label="Відкриті"'));
  assert.equal((html.match(/data-cid="n1"/g) || []).length, 1);
  assert.equal(commentsPanelHTML(base({ dual: true, filter: "all", snapshot: { iteration: "3", comments: [D({ id: "o1", n: 1 })] } })).includes("cmt-sec--new"), false);
});

test("лише «нові» — не «порожньо»", () => {
  assert.doesNotMatch(dual([D({ id: "n1", n: 5, aud: "project" })], { fresh: new Set(["n1"]) }), /Коментарів ще немає/);
});

test("поправка 18: командний пін, закритий агентом → «Зроблено · Іт.4»; закритий вручну → «Закрито» без Іт.", () => {
  const html = dual([
    D({ id: "k", n: 1, aud: "project", status: "resolved", resolvedV: 4, resolveReason: "кнопку перенесено" }),
    D({ id: "m", n: 2, aud: "project", status: "resolved", resolvedV: 1, resolveReason: "resolved manually" }),
  ], { expanded: { earlier: false, closed: true } });
  const card = (id) => html.slice(html.indexOf(`data-cid="${id}"`)).split("</article>")[0];
  assert.match(card("k"), /Зроблено · Іт\.4/);
  assert.match(card("m"), /Закрито/);
  assert.doesNotMatch(card("m"), /Іт\./);
  assert.doesNotMatch(card("m"), /Зроблено/);
});

test("інша сторінка й елемент поза екраном — підписані", () => {
  const html = commentsPanelHTML(base({ snapshot: { iteration: "3", comments: [
    C({ id: "a", n: 1, where: "elsewhere" }), C({ id: "b", n: 2, where: "offscreen" })] } }));
  assert.match(html, /На іншій сторінці/);
  assert.match(html, /Елемента зараз немає на екрані/);
});

test("пін поза екраном несе, де був елемент (`meta.ctx`, як у картці коментатора), екранований", () => {
  const html = commentsPanelHTML(base({ snapshot: { iteration: "3", comments: [
    C({ id: "b", n: 2, where: "offscreen", meta: { ctx: { active: ["Крок 2", "<b>x</b>"], heading: "Ваш партнер" } } }),
    C({ id: "c", n: 3, where: "here", meta: { ctx: { heading: "Не показувати" } } })] } }));
  assert.match(html, /«Крок 2» · «&lt;b&gt;x&lt;\/b&gt;» · розділ «Ваш партнер»/);
  assert.doesNotMatch(html, /<b>x<\/b>/);
  assert.doesNotMatch(html, /Не показувати/);   // контекст — лише коли елемента нема на екрані
});

test("пошук без збігів — «Нічого не знайдено.»; поле пошуку несе запит", () => {
  const html = commentsPanelHTML(base({ query: "\"><x", snapshot: { iteration: "3", comments: [C({ id: "a", n: 1 })] } }));
  assert.match(html, /Нічого не знайдено/);
  assert.match(html, /id="cmt-q"[^>]*value="&quot;&gt;&lt;x"/);
});

const one = (c, over = {}) => commentsPanelHTML(base({ snapshot: { iteration: "3", comments: [c] }, ...over }));

test("мініатюра: растровий data:image малюється кнопкою cmtshot з img", () => {
  const html = one(C({ id: "a", n: 1, meta: { shot: "data:image/png;base64,AA" } }));
  assert.match(html, /data-act="cmtshot" data-val="a"/);
  assert.match(html, /<img src="data:image\/png;base64,AA"/);
});

test("перемикач пінів: aria-pressed від pinsHidden, підпис один; закриття — data-act=comments", () => {
  const off = commentsPanelHTML(base());
  const on = commentsPanelHTML(base({ snapshot: { iteration: "3", pinsHidden: true, comments: [] } }));
  assert.match(off, /data-act="cmtpins" aria-pressed="false" aria-label="Піни · H"/);
  assert.match(on, /data-act="cmtpins" aria-pressed="true" aria-label="Піни · H"/);
  assert.match(off, /data-act="comments"/);
});

test("цитата, ширина, тег режиму; multi без кількості — без нуля", () => {
  const html = one(C({ id: "a", n: 1, meta: { sel: "Купити", viewport: { w: 375, h: 812 }, mode: "area" } }));
  assert.match(html, /<p class="cmt-sel">“Купити”<\/p>/);
  assert.match(html, /375×812/);
  assert.match(html, /<span class="cmt-tag">область<\/span>/);
  const multi = one(C({ id: "b", n: 2, meta: { mode: "multi" } }));
  assert.match(multi, /кілька елементів/);
  assert.equal(/елементів: 0/.test(multi), false);
  assert.match(one(C({ id: "c", n: 3, meta: { mode: "multi", count: 4 } })), /елементів: 4/);
});

test("у режимі редагування кнопки дій цієї картки не малюються", () => {
  const html = one(C({ id: "a", n: 1 }), { editingId: "a" });
  for (const act of ["cmtres", "cmtdel", "cmtedit", "cmtshow"]) assert.equal(html.includes(`data-act="${act}"`), false);
});

test("закрита картка: клас cmt-card--closed і дія cmtreopen", () => {
  const html = one(C({ id: "d", n: 1, status: "resolved" }), { expanded: { earlier: false, closed: true } });
  assert.match(html, /class="cmt-card cmt-card--closed"[^>]*data-cid="d"/);
  assert.match(html, /data-act="cmtreopen" data-val="d"/);
});

test("екранування: причина закриття, цитата й id з розміткою", () => {
  const evil = '"><img onerror=alert(1)>';
  const html = one(C({ id: evil, n: 1, status: "resolved", resolvedV: 2, resolveReason: "<img onerror=alert(2)>", meta: { sel: "<img onerror=alert(3)>" } }),
    { expanded: { earlier: false, closed: true } });
  assert.equal(/<img onerror/.test(html), false);
  assert.match(html, /data-cid="&quot;&gt;&lt;img onerror=alert\(1\)&gt;"/);
  assert.match(html, /&lt;img onerror=alert\(2\)&gt;/);
  assert.match(html, /&lt;img onerror=alert\(3\)&gt;/);
});

test("службова причина «resolved manually» не показується", () => {
  const html = one(C({ id: "d", n: 1, status: "resolved", resolveReason: "resolved manually" }), { expanded: { earlier: false, closed: true } });
  assert.equal(html.includes("resolved manually"), false);
  assert.equal(html.includes("cmt-reason"), false);
  assert.match(html, /Закрито/);
});

test("ручне закриття не видає себе за роботу Claude: внутрішній лічильник коментатора — не Іт.N", () => {
  /* Перевірка проти живого канвасу 0.26.0: пін Іт.6, закритий вручну, показував «Зроблено · Іт.1» — коментатор пише в
     `resolvedV` свій лічильник версій. «Зроблено · Іт.N» — лише для закритих Claude (`inbox.py resolve`). */
  const manual = one(C({ id: "m", n: 1, status: "resolved", resolvedV: 1, resolveReason: "resolved manually" }),
    { expanded: { earlier: false, closed: true } });
  assert.doesNotMatch(manual, /Зроблено/);
  assert.match(manual, /Закрито/);
  const claude = one(C({ id: "k", n: 2, status: "resolved", resolvedV: 6, resolveReason: "Іт.6: заголовок 92 → 84" }),
    { expanded: { earlier: false, closed: true } });
  assert.match(claude, /Зроблено · Іт\.6/);
  assert.match(claude, /заголовок 92 → 84/);
});

/* I-2: КОЖНЕ поле, що потрапляє в розмітку, екранується. Ворожий рядок закриває атрибут, тег і textarea; якщо хоч
   одне поле піде в HTML сирим, у виході зʼявиться живий `<img`/`<script` або розрив `</textarea><script`. */
const H = '"><img src=x onerror=1></textarea><script>';
const SHOT = 'https://x/"onerror="y';
const hostileCard = (o = {}) => ({ id: H, n: H, text: H, author: H, ts: H, iter: H, resolvedV: H, resolveReason: H,
  status: "open", scope: "current", where: "here",
  meta: { mode: H, count: H, sel: H, ctx: { active: [H], heading: H }, viewport: { w: H, h: H }, shot: SHOT }, ...o });
const noBreakout = (html, what) => {
  assert.equal(/<img src=x/.test(html), false, `${what}: живий <img`);
  assert.equal(/<script/i.test(html), false, `${what}: живий <script`);
  assert.equal(/onerror=1/.test(html.replace(/onerror=1&gt;/g, "")), false, `${what}: onerror поза екранованим рядком`);
  assert.equal(/<\/textarea><script/i.test(html), false, `${what}: розрив textarea`);
  // Єдиний `<img` — наша мініатюра, а її src лишається в лапках і не відкриває власного атрибута.
  for (const m of html.matchAll(/<img [^>]*>/g)) assert.match(m[0], /^<img src="[^"]*" alt="[^"]*">$/, `${what}: img зіпсовано`);
};
const hostileHtml = (over, card = {}) => commentsPanelHTML(base({ snapshot: { iteration: H, comments: [
  hostileCard(card)] }, ...over }));

test("I-2: ворожий рядок у кожному полі відкритої картки (ts, viewport, n, mode/count, sel, ctx, author, text, shot, id) не рве розмітку", () => {
  const html = hostileHtml({ selectedId: H, query: H }, { where: "offscreen" });
  noBreakout(html, "відкрита");
  assert.match(html, /src="https:\/\/x\/&quot;onerror=&quot;y"/, "src мініатюри має лишитись у лапках");
  assert.match(html, /<span class="cmt-when">&quot;&gt;&lt;img/);
  assert.match(html, /<p class="cmt-vp">&quot;&gt;&lt;img[^<]*×&quot;&gt;&lt;img/);
  assert.match(html, /<input type="search" id="cmt-q" value="&quot;&gt;&lt;img/);
});

test("I-2: ворожий рядок у картці редагування — textarea, лапки значення, id", () => {
  const html = hostileHtml({ editingId: H });
  noBreakout(html, "редагування");
  assert.match(html, /<textarea class="cmt-edit" data-val="&quot;&gt;&lt;img[^>]*>&quot;&gt;&lt;img[^<]*&lt;\/textarea&gt;&lt;script&gt;<\/textarea>/);
  assert.equal((html.match(/<\/textarea>/g) || []).length, 1, "textarea закрита зайвий раз");
});

test("I-2: закрита картка — resolvedV, resolveReason; попередня — iter і підпис «Перенести в Іт.»", () => {
  const closed = commentsPanelHTML(base({ expanded: { earlier: true, closed: true }, snapshot: { iteration: H, comments: [
    hostileCard({ status: "resolved" }), hostileCard({ id: "e", scope: "earlier" })] } }));
  noBreakout(closed, "закрита й попередня");
  assert.match(closed, /<p class="cmt-done">Зроблено · Іт\.&quot;&gt;&lt;img/);
  assert.match(closed, /<p class="cmt-reason">&quot;&gt;&lt;img/);
  assert.match(closed, /<p class="cmt-iter">Іт\.&quot;&gt;&lt;img/);
  assert.match(closed, /aria-label="Перенести в Іт\.&quot;&gt;&lt;img/);
});

test("I-2: ворожі текст відмови, пошуковий запит без збігів і картка «на іншій сторінці»", () => {
  const down = commentsPanelHTML(base({ snapshot: null, down: H }));
  noBreakout(down, "down");
  assert.match(down, /недоступні: &quot;&gt;&lt;img/);
  const none = commentsPanelHTML(base({ query: H, snapshot: { iteration: H, comments: [] } }));
  noBreakout(none, "порожній пошук");
});

test("Б2 ревʼю I: збережений фільтр без командного постачальника не ховає піни (фільтр лише в dual)", () => {
  const snapshot = { iteration: "3", comments: [D({ id: "a", n: 1 }), D({ id: "b", n: 2 })] };
  for (const filter of ["project", "local"]) {
    const html = commentsPanelHTML(base({ filter, snapshot }));
    assert.match(html, /data-cid="a"/, filter);
    assert.match(html, /data-cid="b"/, filter);
    assert.doesNotMatch(html, /Нічого не знайдено|Коментарів ще немає/, filter);
  }
});

test("Б2 ревʼю M7: фільтр «Команда» лишає командну свіжу картку", () => {
  const html = dual([D({ id: "n1", n: 5, aud: "project" }), D({ id: "o1", n: 1 })], { fresh: new Set(["n1"]), filter: "project" });
  assert.match(html, /cmt-sec--new/);
  assert.match(html, /data-cid="n1"/);
  assert.doesNotMatch(html, /data-cid="o1"/);
});

test("Б2 ревʼю M4: коментарі є, але фільтр сховав усі — «Нічого не знайдено», а не «ще немає»", () => {
  const html = dual([D({ id: "o1", n: 1 })], { filter: "project" });
  assert.match(html, /Нічого не знайдено/);
  assert.doesNotMatch(html, /Коментарів ще немає/);
  assert.match(dual([]), /Коментарів ще немає/);
});

test("кошик у картці: delAsk — рядок дій стає питанням, «Скасувати» перед «Видалити»", () => {
  const html = commentsPanelHTML(base({ delAsk: "a", snapshot: { iteration: "3", comments: [C({ id: "a", n: 1 })] } }));
  assert.match(html, /<div class="cmt-acts cmt-acts--cfm"><div class="cfm"/);
  assert.match(html, /class="cfm-no" data-act="cmtdelno">Скасувати</);
  assert.match(html, /class="cfm-yes" data-act="cmtdelyes" data-val="a">Видалити</);
  assert.ok(html.indexOf('class="cfm-no"') < html.indexOf('class="cfm-yes"'));
  assert.equal(html.includes('data-act="cmtdel"'), false);
});

test("кошик у картці: питання лише в тій картці, чий id у delAsk; інші мають звичайні дії", () => {
  const html = commentsPanelHTML(base({ delAsk: "a", snapshot: { iteration: "3", comments: [C({ id: "a", n: 1 }), C({ id: "b", n: 2 })] } }));
  assert.equal((html.match(/class="cfm"/g) || []).length, 1);
  assert.match(html, /data-act="cmtdel" data-val="b"/);
});

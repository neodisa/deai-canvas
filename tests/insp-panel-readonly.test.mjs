/**
 * 0.32.0, Task 4: панель інспектора лише для перегляду (опублікований превʼю). Значення — текстом, чип токена лишається,
 * редагування немає ні в якому вигляді. Deai без опції — `tests/insp-panel-default.test.mjs`.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { setLang } from "../app/i18n.js";
import { panelHTML } from "../app/insp-panel.js";
import { inspectHTML } from "../app/shell-inspect.js";
import { COLOR, F, FULL_MODEL, MIN_MODEL } from "./_insp-fixtures.mjs";

setLang("uk");
const RO = { readonly: true };

/** Модель, у якій є ВСЕ, що в Deai редагується: пари, сторони, flex, заливка, обведення, текст зі списком, «до токена». */
function everything() {
  const m = FULL_MODEL();
  const P = (id, prop) => F({ id, props: [prop] });
  m.spacing = { ...m.spacing, sides: true, forced: false,
    pad: { top: P("pt", "padding-top"), right: P("pr", "padding-right"), bottom: P("pb", "padding-bottom"), left: P("pl", "padding-left") },
    mar: { top: P("mt", "margin-top"), right: P("mr", "margin-right"), bottom: P("mb", "margin-bottom"), left: P("ml", "margin-left") } };
  m.size = { w: F({ id: "w", props: ["width"], verdict: "off-ds", token: "--w-x", snap: { token: "--w-1", value: "12px" } }), h: m.size.h };
  return m;
}

test("у режимі перегляду нема жодного поля вводу чи списку", () => {
  for (const m of [everything(), FULL_MODEL(), MIN_MODEL()]) {
    const h = panelHTML(m, RO);
    assert.doesNotMatch(h, /<(input|textarea|select|option)\b/i);
    assert.doesNotMatch(h, /contenteditable/i);
  }
  const wrapped = inspectHTML({ shellMode: "layout", on: true, model: everything(), readonly: true });
  assert.doesNotMatch(wrapped, /<(input|textarea|select|option)\b/i);
});

test("жодних дій редагування: ні insptune*, ні inspsnap, ні inspadd, ні inspsides, ні inspalign/inspdir, ні скрабу", () => {
  const h = panelHTML(everything(), RO);
  for (const act of ["insptune", "insptunecolor", "inspsnap", "inspadd", "inspsides", "inspalign", "inspdir"]) {
    assert.doesNotMatch(h, new RegExp(`data-act="${act}"`), act);
  }
  assert.doesNotMatch(h, /data-scrub/);
  assert.doesNotMatch(h, /insp-snap/);
});

test("у Deai ті самі дії є — свідок, що перевірка вище не порожня", () => {
  const h = panelHTML(everything());
  for (const act of ["insptune", "insptunecolor", "inspsnap", "inspalign", "inspdir", "inspsides"]) {
    assert.match(h, new RegExp(`data-act="${act}"`), act);
  }
  assert.match(h, /data-scrub/);
});

test("значення — текстом у тих самих полях, з тими самими адресами", () => {
  const h = panelHTML(FULL_MODEL(), RO);
  assert.match(h, /<div class="insp-f"[^>]*data-prop="width"[^>]*><span class="insp-fl"[^>]*>[^<]*<\/span><span class="insp-ro">560<\/span>/);
  assert.match(h, /data-prop="font-size"[^>]*data-ro[^>]*>[\s\S]*?<span class="insp-ro">14<\/span>/);
});

test("кольорове поле: квадрат і значення текстом; список насиченості — підпис вибраного пункту", () => {
  const h = panelHTML(FULL_MODEL(), RO);
  assert.match(h, /<span class="insp-sw" style="background:#1F4FE0"><\/span><span class="insp-ro">1F4FE0<\/span>/);
  assert.match(h, /<span class="insp-ro">Semibold<\/span>/);
  assert.doesNotMatch(h, />600</, "значення «600» не сміє підмінити підпис пункту");
});

test("чип токена лишається: token, off-ds, а в полі kind=ro — теж (у Deai він там губиться)", () => {
  const m = MIN_MODEL();
  m.size = { w: F({ id: "w", props: ["width"], verdict: "token", token: "sp-3" }),
    h: F({ id: "h", props: ["height"], kind: "ro", value: "auto", verdict: "token", token: "sp-1" }) };
  const h = panelHTML(m, RO);
  assert.match(h, /<span class="insp-tok" title="sp-3">sp-3<\/span>/);
  assert.match(h, /<span class="insp-ro">auto<\/span><span class="insp-tok" title="sp-1">sp-1<\/span>/);
  assert.doesNotMatch(panelHTML(m), /<span class="insp-ro">auto<\/span><span class="insp-tok"/, "у Deai поле ro без чипа — зміна лише у режимі перегляду");
  const off = FULL_MODEL();
  off.fill = COLOR({ verdict: "off-ds", token: "brand-x", snap: { token: "--brand-600", value: "#1F4FE0" } });
  assert.match(panelHTML(off, RO), /<span class="insp-tok" data-off title="brand-x">brand-x<\/span>/);
  assert.doesNotMatch(panelHTML(off, RO), /--brand-600/, "«до токена» нема, і його імені теж");
});

test("вирівнювання й напрям лишаються видимими — вимкненими кнопками без data-act", () => {
  const h = panelHTML(FULL_MODEL(), RO);
  assert.equal((h.match(/class="insp-cell"/g) || []).length, 9);
  assert.equal((h.match(/class="insp-dir"/g) || []).length, 2);
  assert.equal((h.match(/class="insp-cell" disabled/g) || []).length, 9);
  assert.equal((h.match(/class="insp-dir" disabled/g) || []).length, 2);
  assert.equal((h.match(/class="insp-cell" disabled[^>]*aria-pressed="true"/g) || []).length, 1, "натиснуте вічко видно");
});

test("«+» заливки й обведення та перемикач сторін зникають; розділи лишаються", () => {
  const m = MIN_MODEL();
  const h = panelHTML(m, RO);
  assert.doesNotMatch(h, /insp-ib/);
  assert.deepEqual([...h.matchAll(/data-sec="([a-z]+)"/g)].map((x) => x[1]), ["size", "spacing", "fill", "stroke"]);
  assert.match(panelHTML(m), /insp-ib/, "у Deai кнопки є");
});

test("навігація (крихти) лишається: це не редагування", () => {
  assert.match(panelHTML(FULL_MODEL(), RO), /data-act="inspcrumb" data-val="1"/);
});

test("оболонка в режимі перегляду: без підвалу тюнера, навіть коли пакет прийшов; кнопка закриття лишається", () => {
  const PKG = { kind: "k", version: 1, status: "ready", page: "p", note: "записка", editCount: 1, instructions: [],
    elements: [{ page: "p", selector: "a", label: "a", trail: ["a"], text: "", edits: [{ prop: "gap", from: "8px", to: "12px", rule: ".c",
      raw: "", token: "", tokenValue: "", verdict: "unlinked", hint: [] }] }] };
  const st = { shellMode: "layout", on: true, model: FULL_MODEL(), tune: PKG, tuneOther: 2, tuneMissing: [] };
  const ro = inspectHTML({ ...st, readonly: true });
  assert.doesNotMatch(ro, /insp-foot|insptune|insp-note-ta|insp-send/);
  assert.match(ro, /data-act="inspector"/);
  assert.match(inspectHTML(st), /insp-foot/, "у Deai підвал є");
  assert.equal(inspectHTML({ ...st, on: false, readonly: true }), "");
});

test("екранування лишається: назва й значення з чужого макета", () => {
  const m = FULL_MODEL();
  m.fill = COLOR({ value: '"><img src=x onerror=1>', swatch: "red\" onerror=\"1" });
  const h = panelHTML(m, RO);
  assert.doesNotMatch(h, /<img src=x/);
  assert.doesNotMatch(h, /onerror=1>/);
});

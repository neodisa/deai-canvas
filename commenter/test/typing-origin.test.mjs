/**
 * Шорткати C/P/H не їдять набір у полях ОБОЛОНКИ навколо рамки.
 *
 * ЩО ЛАМАЛОСЬ. Обробник keydown вішається на вікно рамки І на кожен same-origin
 * предок (щоб шорткати жили, коли фокус у інструменті навколо iframe). А
 * `_isTyping()` дивився лише на `document.activeElement` ДОКУМЕНТА РАМКИ — коли
 * дизайнер друкував у полі оболонки (пошук задач `#task-q`, палітра ⌘K `#palq`),
 * activeElement рамки був `body`, «друкування» не бачилось, і букви c/p/h
 * з'їдались (preventDefault) та вмикали режим коментування: «chip» → «i».
 *
 * Тепер перевіряється ще й елемент-ПОХОДЖЕННЯ події (`composedPath()[0]`).
 * Тягнути весь віджет у node неможливо (DOM) — як і в сусідніх тестах,
 * витягуємо чисті функції з джерела й годуємо їх підробленими вузлами.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)),
                         "..", "src", "comment-layer.js");
const src = readFileSync(SRC, "utf8");

const grab = (name) => {
  const m = src.match(new RegExp(` {2}function ${name}\\([\\s\\S]*?\\n {2}\\}`));
  assert.ok(m, `у comment-layer.js немає ${name} — перевірка набору в полях не існує`);
  return m[0];
};
// eslint-disable-next-line no-new-func
const { isTypingField, keyOrigin, typingIn } = new Function(
  `${grab("isTypingField")}\n${grab("keyOrigin")}\n${grab("typingIn")}\n`
  + "return { isTypingField, keyOrigin, typingIn };")();

/* Підроблений елемент ІНШОГО документа (оболонка), видимий на екрані. */
function el(tag, attrs = {}, box = { width: 200, height: 30, top: 10, left: 10 }) {
  const view = {
    innerWidth: 1400, innerHeight: 900,
    getComputedStyle: () => ({ visibility: "visible", opacity: "1" }),
  };
  return {
    nodeType: 1, tagName: tag.toUpperCase(), type: attrs.type,
    isContentEditable: !!attrs.contentEditable,
    ownerDocument: { defaultView: view },
    getBoundingClientRect: () => ({
      ...box, bottom: box.top + box.height, right: box.left + box.width,
    }),
  };
}
const ev = (target) => ({ target, composedPath: () => [target] });

// подія з поля оболонки → друкуємо, хоч activeElement рамки — body
const body = el("body");
assert.equal(typingIn(ev(el("input", { type: "text" })), body), true,
  "input[text] з іншого документа — це набір, шорткати мовчать");
assert.equal(typingIn(ev(el("input", { type: "search" })), body), true, "search");
assert.equal(typingIn(ev(el("input", { type: "number" })), body), true, "number");
assert.equal(typingIn(ev(el("input")), body), true, "input без type = text");

// не поле → шорткат живий
assert.equal(typingIn(ev(el("input", { type: "checkbox" })), body), false, "checkbox");
assert.equal(typingIn(ev(el("div")), body), false, "звичайний div");
assert.equal(typingIn(ev(body), body), false, "фокус у тілі рамки: c/p/h — наші");

// без події — стара логіка по activeElement
assert.equal(typingIn(undefined, el("textarea")), true, "без події: фокусний textarea");
assert.equal(typingIn(undefined, body), false, "без події: body");

// ОБИДВА кандидати рахуються: поле в рамці, подія з тіла — теж набір
assert.equal(typingIn(ev(body), el("textarea")), true, "activeElement рамки — поле");

// позаекранне 1px-поле (канвас-редактори) не вважається набором
assert.equal(typingIn(ev(el("input", { type: "text" },
  { width: 1, height: 1, top: 0, left: -9999 })), body), false, "1px-поле поза екраном");

// composedPath()[0] виграє над e.target (подія з тіньового кореня ретаргетиться)
const host = el("div");
const inner = el("input", { type: "text" });
assert.equal(typingIn({ target: host, composedPath: () => [inner, host] }, body), true,
  "composedPath()[0] — справжнє походження");
// без composedPath — e.target
assert.equal(typingIn({ target: el("textarea") }, body), true, "fallback на e.target");

console.log("typing-origin: ok");

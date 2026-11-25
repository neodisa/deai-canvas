import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8");

test("0.40: .row-name лишається з трикрапкою (довга назва обрізається, повна — у підказці)", () => {
  assert.match(css, /\.row-name\{[^}]*overflow:hidden[^}]*text-overflow:ellipsis/);
});
test("0.40: ручка панелі — col-resize, над .panel", () => {
  assert.match(css, /#panel-resize\{[^}]*cursor:col-resize/);
  assert.match(css, /#panel-resize\{[^}]*z-index:calc\(var\(--z-panel\) \+ 1\)/);
});
test("0.40: під час перетягування панель без transition", () => {
  assert.match(css, /body\.panel-dragging \.panel\{[^}]*transition:none/);
});
test("0.40: ручка ховається в рейці, на екрані «Задачі» і в чистому перегляді", () => {
  for (const sel of ["body:not(.with-panel) #panel-resize", "body.panel-collapsed #panel-resize", "body.home-open #panel-resize", "html.cv-clean #panel-resize"]) {
    assert.ok(css.includes(sel), sel);
  }
});

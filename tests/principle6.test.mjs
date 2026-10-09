/**
 * Принцип 6 PRODUCT.md (T-45): коментатор — один продукт у двох режимах, і
 * оболонка пінів НЕ малює. Вона дає координати й камеру (`overview-comments.js`),
 * а кружки, лічильники й панель створює сам comment-layer у своєму shadow root.
 *
 * Навіщо охоронець. Найкоротший шлях «показати лічильник пінів на кадрі» —
 * дописати `<span class="pin">` у `cardEl` оболонки. Він дає другу реалізацію
 * того самого знання (що таке відкритий пін ітерації, як він рахується), і дві
 * реалізації розходяться мовчки — рівно причина, з якої існує принцип.
 *
 * Мутаційно: дописати в будь-який `app/*.js` `el.className = 'pin'` чи
 * `classList.add('cp')` — тест червоніє. Читати класи коментатора (фільтр
 * колеса `closest('.cp')`) оболонці можна: це маршрутизація подій, не малювання.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app");
const MAKES_PIN = [
  /className\s*=\s*[`'"][^`'"]*\b(pin|cp|cbadge)\b/,
  /classList\.(add|toggle)\(\s*[`'"](pin|cp|cluster|cbadge)[`'"]/,
  /class=\\?["'][^"']*\b(pin|cp|cbadge)\b[^"']*\\?["']/,
];

test("оболонка не створює пінів коментатора — їх малює сам comment-layer", () => {
  const bad = [];
  for (const f of readdirSync(APP).filter((x) => x.endsWith(".js"))) {
    const src = readFileSync(path.join(APP, f), "utf8");
    src.split("\n").forEach((line, i) => {
      if (MAKES_PIN.some((re) => re.test(line))) bad.push(`${f}:${i + 1}  ${line.trim().slice(0, 100)}`);
    });
  }
  assert.deepEqual(bad, [], "оболонка малює пін сама — принцип 6 PRODUCT.md");
});

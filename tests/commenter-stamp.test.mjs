/**
 * Вендорні бандли коментатора (`app/vendor/comment-layer.min.js`, `app/vendor/anchor.min.js`) зібрано з ПОТОЧНОГО
 * `commenter/src` (Deai 0.26.0). Ланцюжок із двох ланок: хеш `src/` == `build-stamp.json#src` і хеш кожного вендорного
 * файла == `build-stamp.json#out[файл]`. Правка в `src/` без збірки червонить першу ланку; ручна правка бандла — другу.
 * Хеш `src/` рахує ТА САМА функція, що й збірка (`srcHash` з `commenter/scripts/build.mjs`): двох реалізацій бути не мусить.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { srcHash } from "../commenter/scripts/build.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const STAMP = JSON.parse(readFileSync(path.join(ROOT, "commenter", "build-stamp.json"), "utf8"));
const sha = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");

test("штамп збірки відповідає поточному commenter/src", () => {
  assert.equal(STAMP.src, srcHash(path.join(ROOT, "commenter")), "src змінено без `npm run build` у commenter/");
  assert.equal(STAMP.esbuild, "0.25.12");
});

test("вендорні бандли — рівно ті, що записала збірка", () => {
  assert.deepEqual(Object.keys(STAMP.out).sort(), ["anchor.min.js", "comment-layer.min.js"]);
  for (const [name, want] of Object.entries(STAMP.out)) {
    assert.equal(sha(path.join(ROOT, "app", "vendor", name)), want, `app/vendor/${name} не зі збірки`);
  }
});

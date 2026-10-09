import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { fileEntries, folderStamp, stampFrom, TOOL_META } from "../bin/shots-stamp.mjs";

function fixture() {
  const dir = mkdtempSync(path.join(tmpdir(), "dc-stamp-"));
  mkdirSync(path.join(dir, "poshuk"));
  mkdirSync(path.join(dir, "shared"));
  mkdirSync(path.join(dir, "shots"));
  writeFileSync(path.join(dir, "poshuk", "index.html"), "<h1>Пошук</h1>");
  writeFileSync(path.join(dir, "shared", "header.html"), "<header/>");
  writeFileSync(path.join(dir, "shots", "poshuk.webp"), "не входить у штамп");
  writeFileSync(path.join(dir, "index.html"), "<h1>Корінь</h1>");
  return dir;
}

test("порядок записів не впливає на штамп", () => {
  const a = [["a", "11"], ["b", "22"]];
  assert.equal(stampFrom(a), stampFrom([...a].reverse()));
});

test("штамп змінюється, коли змінився файл сторінки", () => {
  const dir = fixture();
  const parts = [{ dir: path.join(dir, "poshuk"), label: "page", recursive: true },
                 { dir: path.join(dir, "shared"), label: "shared", recursive: true }];
  const before = folderStamp(parts);
  writeFileSync(path.join(dir, "poshuk", "index.html"), "<h1>Пошук v2</h1>");
  assert.notEqual(folderStamp(parts), before);
});

test("правка у shared зачіпає штамп сторінки", () => {
  const dir = fixture();
  const parts = [{ dir: path.join(dir, "poshuk"), label: "page", recursive: true },
                 { dir: path.join(dir, "shared"), label: "shared", recursive: true }];
  const before = folderStamp(parts);
  writeFileSync(path.join(dir, "shared", "header.html"), "<header>v2</header>");
  assert.notEqual(folderStamp(parts), before);
});

test("похідні знімки у штамп не входять", () => {
  const dir = fixture();
  const parts = [{ dir, label: "root", recursive: true }];
  const before = folderStamp(parts);
  writeFileSync(path.join(dir, "shots", "poshuk.webp"), "інші байти");
  assert.equal(folderStamp(parts), before);
});

test("неявна main рахує лише корінь, а не теки інших сторінок", () => {
  const dir = fixture();
  const parts = [{ dir, label: "root", recursive: false }];
  const before = folderStamp(parts);
  writeFileSync(path.join(dir, "poshuk", "index.html"), "<h1>чужа сторінка</h1>");
  assert.equal(folderStamp(parts), before);
});

test("теки, якої немає, достатньо щоб не впасти", () => {
  const dir = fixture();
  assert.equal(fileEntries(path.join(dir, "нема-такої")).length, 0);
});

test("тека, яка виявилась файлом, падає, а не тихо віддає нуль записів", () => {
  const dir = fixture();
  const notADir = path.join(dir, "файл-замість-теки");
  writeFileSync(notADir, "я файл");
  assert.throws(() => fileEntries(notADir), { code: "ENOTDIR" });
});

test("прихований файл у штамп не входить", () => {
  const dir = fixture();
  const parts = [{ dir: path.join(dir, "poshuk"), label: "page", recursive: true }];
  const before = folderStamp(parts);
  writeFileSync(path.join(dir, "poshuk", ".dc-local.json"), "службове");
  assert.equal(folderStamp(parts), before);
});

test("осиротілий tmp не зсуває штамп — інакше конвеєр перезнімає без причини", () => {
  const dir = fixture();
  const parts = [{ dir, label: "page", recursive: true }];
  const before = folderStamp(parts);
  // Рівно те, що лишає вбитий прогін атомарного писаря. Теку `shots/` рятує
  // SKIP_DIRS, корінь ітерації — не рятувало ніщо.
  writeFileSync(path.join(dir, "pages.json.ab12cd.tmp"), "напівзаписане");
  assert.equal(folderStamp(parts), before, "штамп зсунувся від недописаного файла");
  // А справжня правка штамп зсуває — інакше тест вище стеріг би просто сліпоту.
  writeFileSync(path.join(dir, "index.html"), "<h1>Інший</h1>");
  assert.notEqual(folderStamp(parts), before);
});

test("службові файли інструмента в корені не зсувають штамп сторінки", () => {
  const dir = fixture();
  /* Корінь ітерації входить у штамп КОЖНОЇ сторінки (`stampsFor`) заради
     спільних стилів — тому граф флоу й перелік сторінок, що лежать тут же,
     застарювали геть усі кадри, хоч жодна сторінка їх не читає. Це TD-9, і
     виміряний він був вужче за саму ваду: там сказано про неявну `main`. */
  const parts = [{ dir, label: "root", recursive: false, skipNames: TOOL_META }];
  const before = folderStamp(parts);
  writeFileSync(path.join(dir, "flow.json"), JSON.stringify({ flows: [{ id: "f1" }] }));
  writeFileSync(path.join(dir, "pages.json"), JSON.stringify({ pages: [{ id: "a" }] }));
  assert.equal(folderStamp(parts), before,
    "правка графа флоу чи переліку сторінок замовила пересʼємку без жодної зміни дизайну");

  // Свідок: справжній спільний файл у тому ж корені штамп ЗСУВАЄ. Без нього
  // перевірка вище була б зелена і від сліпого штампа, що не бачить нічого.
  writeFileSync(path.join(dir, "landing.css"), "body{color:red}");
  assert.notEqual(folderStamp(parts), before,
    "спільний стиль у корені мусить робити кадри застарілими");
});

test("частина «сторінка» службових файлів не пропускає — виняток діє лише де просили", () => {
  const dir = fixture();
  /* Межа проходить по ЧАСТИНІ штампа, а не по глибині: `skipNames` передає
     лише частина «корінь ітерації» (`stampsFor`). Частина «сторінка» його не
     передає, тож `flow.json`, покладений у теку сторінки, лишається її
     вмістом. Перша спроба розрізняти глибиною (`dir === base`) протікала:
     верхній рівень теки СТОРІНКИ — теж `base`, і файл зникав зі штампа. */
  const parts = [{ dir: path.join(dir, "poshuk"), label: "page", recursive: true }];
  const before = folderStamp(parts);
  writeFileSync(path.join(dir, "poshuk", "flow.json"), "{}");
  assert.notEqual(folderStamp(parts), before,
    "файл усередині сторінки пропущено як службовий — виняток протік углиб");
});

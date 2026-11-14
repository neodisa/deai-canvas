/**
 * Дрібні охоронці проводки коментатора (Deai 0.27.0, T11 / крок 0), яких не видно з поведінки: браузер однаково
 * приймає і ширший селектор, і зайвий `style.background = ''`. Стережемо текстом джерела.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "src", "comment-layer.js");
const src = readFileSync(SRC, "utf8");

// Рядок аудиторій панелі ловиться селектором рядка, а не голим `[data-aud]`: піни теж мають `data-aud`.
assert.match(src, /root\.querySelectorAll\('\.auds \[data-aud\]'\)/, "проводка аудиторій має вужчий селектор — `.auds [data-aud]`");
assert.doesNotMatch(src, /root\.querySelectorAll\('\[data-aud\]'\)/, "голий `[data-aud]` зачепить і піни");

// Пін полотна без кольору не отримує запису фону (без хоста — жодних змін DOM).
assert.doesNotMatch(src, /style\.background = col \|\| ''/, "фон піна полотна пишеться безумовно");
assert.match(src, /if \(col\) w\.firstChild\.style\.background = col; else if \(w\.firstChild\.style\.background\) w\.firstChild\.style\.background = '';/,
  "фон піна полотна: пишемо лише коли є колір або є що скинути");

// setMeta не ітерує небезпечні ключі.
assert.match(src, /k === '__proto__' \|\| k === 'constructor' \|\| k === 'prototype'/, "setMeta не відсікає небезпечні ключі");
console.log("host-wiring: ok");

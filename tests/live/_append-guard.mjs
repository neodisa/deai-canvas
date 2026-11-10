/**
 * Охоронець «у ЧУЖИЙ файл не дописано слідів цього тесту» — для будь-яких справжніх журналів машини (загальний допоміжний засіб для живих тестів).
 *
 * ⛔ Чому не `mtime:size`. Справжній лог може дописувати ІНШИЙ процес (справжній канвас на тій же машині), і порівняння «файл не
 * змінився» червоніло б без нашої вини (спостережено 03.11.2026). Тож дивимось не на ЗМІНУ, а на ЗМІСТ: що дописано після
 * знятого розміру, і чи є там наші мітки (тимчасова домівка, вигадані хости, `DEMO-…`). Чужий рядок — не привід для провалу.
 *
 * Лише читання. Повідомлення про провал називає ЛИШЕ знайдену мітку й НІКОЛИ не друкує вміст: це лог справжньої машини.
 * Правила: файла не було й нема — ок; файла не було, а зʼявився — провал; файл став меншим чи зник — ротація ззовні, ок;
 * виріс — читаємо ЛИШЕ дописаний хвіст (не більше `cap` байтів) і шукаємо мітки.
 */
import { closeSync, openSync, readSync, statSync } from "node:fs";

const sizeOf = (file) => { try { return statSync(file).size; } catch { return null; } };

/** Знімає розмір зараз; повертає функцію-перевірку, що кидає `Error` із назвою знайденої мітки (або тихо повертається). */
export function appendGuard(file, markers, { cap = 256 * 1024 } = {}) {
  const before = sizeOf(file);
  return () => {
    const now = sizeOf(file);
    if (before === null) {
      if (now !== null) throw new Error("справжній файл логу зʼявився під час тесту (до тесту його не було)");
      return;
    }
    if (now === null || now <= before) return;               // зник, обрізаний (ротація ззовні) чи не змінився
    const len = Math.min(now - before, cap);
    const buf = Buffer.alloc(len);
    const fd = openSync(file, "r");
    try {
      let got = 0;
      while (got < len) {
        const n = readSync(fd, buf, got, len - got, before + got);
        if (n <= 0) break;
        got += n;
      }
      const tail = buf.subarray(0, got).toString("utf8");
      const hit = markers.filter(Boolean).find((m) => tail.includes(m));
      if (hit !== undefined) throw new Error(`у справжній лог дописано слід цього тесту: мітка «${hit}»`);
    } finally { closeSync(fd); }
  };
}

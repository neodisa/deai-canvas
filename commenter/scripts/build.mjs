/**
 * Збірка бандлів + штамп джерела.
 *
 * Штамп — content-hash файлів `src/`, а НЕ mtime і не git: форматер міняє mtime
 * (охоронець сварився б на незмінений код), а git не бачить незакоміченої правки —
 * саме в такому стані живе розробка, і саме там бандл найлегше лишити старим.
 */
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

/**
 * Хеш `src/`: відносний POSIX-шлях файлу, потім байти; обхід рекурсивний, крапкові елементи
 * пропущені на будь-якому рівні. Рахується лише тут; охоронець — `tests/commenter-stamp.test.mjs`.
 *
 * ⛔ РЕКУРСИВНО: `esbuild --bundle` збирає й те, що лежить у `src/modules/`.
 * Плаский обхід означав би, що правка в підкаталозі не міняє хеш і охоронець мовчки
 * зеленіє на рівно тому інциденті, заради якого він написаний.
 *
 * ⛔ Обхід власноруч, а не `readdirSync(dir, { recursive: true })`: той СПУСКАЄТЬСЯ
 * в симлінк-каталоги. Тут рішення «спускатись» приймає Dirent.isDirectory() (для симлінка
 * false), а рішення «рахувати файл» — statSync, який за посиланням ЙДЕ. Битий симлінк
 * не стає ні тим, ні тим — statSync віддає undefined.
 */
function srcFiles(dir, prefix = "") {
  const out = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name.startsWith(".")) continue;
    const abs = path.join(dir, e.name);
    const rel = prefix ? `${prefix}/${e.name}` : e.name;
    if (e.isDirectory()) out.push(...srcFiles(abs, rel));
    else if (statSync(abs, { throwIfNoEntry: false })?.isFile()) out.push(rel);
  }
  return out;
}

/**
 * ⛔ Сортуємо по байтах UTF-8, а не `.sort()` за замовчуванням: JS порівнює по
 * code unit UTF-16, Python — по code point, і на іменах з астральними символами
 * (емодзі) порядок, а з ним і хеш, розійшлись би.
 */
export function srcHash(root = ROOT) {
  const dir = path.join(root, "src");
  const h = createHash("sha256");
  const rels = srcFiles(dir)
    .sort((a, b) => Buffer.compare(Buffer.from(a, "utf8"), Buffer.from(b, "utf8")));
  for (const rel of rels) {
    h.update(rel);
    h.update(readFileSync(path.join(dir, rel)));
  }
  return h.digest("hex");
}

function esbuildVersion() {
  const pkg = JSON.parse(readFileSync(
    path.join(ROOT, "node_modules", "esbuild", "package.json"), "utf8"));
  return pkg.version;
}

// ⛔ pathToFileURL, а не `file://${argv[1]}`: шлях репозиторію може містити
// пробіл, і import.meta.url приходить перекодованим (%20). Рядкове
// порівняння давало false — `npm run build` мовчки не збирав НІЧОГО й не казав ні
// слова, лишаючи вендорні бандли старими назавжди. Той самий мовчазний пропуск, проти якого
// написаний охоронець `tests/commenter-stamp.test.mjs`.
//
// argv[1] може бути відсутнім (`node -e`, чистий import заради srcHash) — тоді це
// точно не запуск скрипта. Без цієї перевірки pathToFileURL кидає, і файл, який
// експортує srcHash, стає неімпортовним.
const invokedAs = process.argv[1] ? pathToFileURL(process.argv[1]).href : null;
if (import.meta.url === invokedAs) {
  const bin = path.join(ROOT, "node_modules", ".bin", "esbuild");
  /* Вихід — прямо у вендор Deai: окремої `dist/` нема, щоб не було двох копій бандла, одна з яких застаріє.
     `supabase-adapter` не збираємо: у Deai свій адаптер модуля `supabase-comments`. */
  const VENDOR = path.join(ROOT, "..", "app", "vendor");
  const ENTRIES = [["comment-layer.js", "comment-layer.min.js"], ["anchor-global.js", "anchor.min.js"]];
  const out = {};
  for (const [entry, file] of ENTRIES) {
    const dest = path.join(VENDOR, file);
    execFileSync(bin, [path.join("src", entry), "--bundle", "--format=iife", "--minify", `--outfile=${dest}`],
                 { cwd: ROOT, stdio: "inherit" });
    out[file] = createHash("sha256").update(readFileSync(dest)).digest("hex");
  }
  writeFileSync(path.join(ROOT, "build-stamp.json"),
    `${JSON.stringify({ src: srcHash(), esbuild: esbuildVersion(), out }, null, 2)}\n`);
  console.log("app/vendor зібрано, штамп записано");
}

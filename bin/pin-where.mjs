#!/usr/bin/env node
/**
 * ДЕ стоїть пін: віджет + інші екземпляри того самого елемента (fb-30092026-e53eaa).
 *
 *   echo '[{"id":"…","fp":{…},"it":"it15","page":"me--welcome"}]' \
 *     | node bin/pin-where.mjs --url http://localhost:8765
 *   → {"<id>": {"found": true, "widget": "Ризики компанії", "twins": ["Санкції"]}, …}
 *
 * ⛔ Чому браузер, а не розбір HTML: у SPA-ітераціях (boss-interface) DOM малює
 * JavaScript, статичний index.html віджетів не містить. Тому сторінку відкриваємо
 * в Chromium (`/commented?…&bare=1` — без коментатора, рівно макет) і шукаємо
 * елемент ТИМ САМИМ `findMatch`, що й коментатор: інший пошук давав би іншу
 * відповідь на питання «де пін».
 *
 * Віджет — перший предок, що має імʼя: кастомний тег (Angular-віджет
 * `compliance-…`), `aria-label`/`data-widget`, або заголовок секції/регіону.
 * Двійники — елементи того ж тегу з тим самим текстом і структурою.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
export const ANCHOR = readFileSync(path.join(ROOT, "app", "vendor", "anchor.min.js"), "utf8");

/** Виконується В СТОРІНЦІ: усе, що потрібно, — у тілі функції. */
function lookup(fps) {
  const A = window.CommentLayerAnchor;
  const clip = (t) => String(t || "").replace(/\s+/g, " ").trim().slice(0, 60);
  const widgetName = (el) => {
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      if (a.tagName.includes("-")) return a.tagName.toLowerCase();
      const lab = a.getAttribute("aria-label") || a.getAttribute("data-widget");
      if (lab && clip(lab)) return clip(lab);
      if (/^(SECTION|ARTICLE)$/.test(a.tagName) || a.getAttribute("role") === "region") {
        const h = a.querySelector("h1,h2,h3,h4,[role=heading]");
        if (h && clip(h.textContent)) return clip(h.textContent);
      }
    }
    return null;
  };
  return fps.map((fp) => {
    let m;
    try { m = A.findMatch(fp, document.body); } catch (e) { return { found: false }; }
    if (!m.el || m.score < A.MATCH_THRESHOLD) return { found: false };
    const twins = [];
    for (const e of document.body.getElementsByTagName(m.el.tagName)) {
      if (e === m.el) continue;
      const f = A.fingerprint(e, document.body);
      if (f.textHash === fp.textHash && f.structHash === fp.structHash) twins.push(widgetName(e) || "без назви");
    }
    return { found: true, widget: widgetName(m.el), twins };
  });
}

/** pins: [{id, fp, it, page}] → {id: {found, widget, twins}}. Сторінку відкриваємо раз на (it, page). */
export async function pinWhere({ url, pins, launch, timeout = 15000 }) {
  const groups = new Map();
  for (const p of pins) {
    const key = `${p.it}\u0000${p.page || ""}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(p);
  }
  const out = {};
  const browser = await launch();
  try {
    for (const group of groups.values()) {
      const { it, page } = group[0];
      const tab = await browser.newPage({ viewport: { width: 1440, height: 900 } });
      try {
        const q = `it=${encodeURIComponent(it)}${page ? `&page=${encodeURIComponent(page)}` : ""}`;
        await tab.goto(`${url}/commented?${q}&bare=1`, { waitUntil: "load", timeout });
        await tab.addScriptTag({ content: ANCHOR });
        const res = await tab.evaluate(lookup, group.map((p) => p.fp));
        group.forEach((p, i) => { out[p.id] = res[i]; });
      } catch (e) {
        for (const p of group) out[p.id] = { found: false, error: String(e.message || e).slice(0, 120) };
      } finally { await tab.close(); }
    }
  } finally { await browser.close(); }
  return out;
}

async function main() {
  const i = process.argv.indexOf("--url");
  const url = i > 0 ? process.argv[i + 1] : "http://localhost:8765";
  const pins = JSON.parse(readFileSync(0, "utf8") || "[]");
  const { chromium } = await import("playwright");
  const out = await pinWhere({ url, pins, launch: () => chromium.launch() });
  process.stdout.write(JSON.stringify(out));
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  main().catch((e) => { process.stderr.write(`pin-where: ${e.message || e}\n`); process.exit(1); });
}

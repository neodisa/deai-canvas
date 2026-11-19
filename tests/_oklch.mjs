/* Читання токенів палітри оболонки з `styles.css` для охоронців контрасту й кольору простору: hex, `var()`-аліаси й
   `oklch(L calc(C*var(--sp-k)) var(--sp-h))` (відтінок і множник — із типових значень або з правила простору). */

/** oklch → sRGB [0..255] (Björn Ottosson), з обрізанням у гамут. */
export function oklchToRgb(L, C, hDeg) {
  const h = (hDeg * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
  const lin = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
  ];
  return lin.map((c) => {
    const v = Math.min(1, Math.max(0, c));
    return Math.round(255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055));
  });
}

export const toHex = (rgb) => `#${rgb.map((v) => v.toString(16).padStart(2, "0")).join("")}`;

/** Значення `--name` (перша згадка в css) → текст значення або null. */
export function tokenText(css, name) {
  const m = css.match(new RegExp(`(?<![\\w-])--${name}\\s*:\\s*([^;}]+)`));
  return m ? m[1].trim() : null;
}

/** Токен → [r,g,b]. `sp` — `{h, k}` простору (типово — з `:root`). */
export function tokenRgb(css, name, sp = null, depth = 0) {
  const raw = tokenText(css, name);
  if (raw == null || depth > 6) return null;
  const alias = raw.match(/^var\(--([\w-]+)\)$/);
  if (alias) return tokenRgb(css, alias[1], sp, depth + 1);
  const hex = raw.match(/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/);
  if (hex) { const h6 = hex[1].length === 3 ? [...hex[1]].map((c) => c + c).join("") : hex[1]; const n = parseInt(h6, 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
  const ok = raw.match(/^oklch\(\s*([\d.]+)\s+calc\(\s*([\d.]+)\s*\*\s*var\(--sp-k\)\s*\)\s+var\(--sp-h\)\s*\)$/);
  if (ok) {
    const h = sp?.h ?? Number(tokenText(css, "sp-h"));
    const k = sp?.k ?? Number(tokenText(css, "sp-k"));
    return oklchToRgb(Number(ok[1]), Number(ok[2]) * k, h);
  }
  return null;
}

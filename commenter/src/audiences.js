/*!
 * Audience row — the panel's OPTIONAL "who is this feedback for" switch.
 *
 * A host can have several places feedback may go. Design Canvas has two: a
 * local file its AI agent reads, and Supabase for the team. It wants that
 * choice inside this panel, next to the comments themselves.
 *
 * The contract is deliberately thin, because "channel" must NOT leak in here:
 *
 *   init({ audiences: [{ id, label, active }], onAudience })
 *
 *   - no `audiences` (or an empty one) -> the row is not drawn AT ALL. This is
 *     load-bearing: comment-layer ships standalone, and a host that never
 *     heard of audiences must get exactly the panel it always got.
 *   - `onAudience(id)` REPORTS a choice; it does not act on one. Whether a
 *     choice means a reload, a store swap or nothing at all is the host's
 *     business — and so is the state that remembers it. If this widget
 *     navigated on its own, the choice would live in two places and the two
 *     would drift.
 *
 * WHY a module of its own instead of a few lines inside the panel markup: the
 * panel needs a browser, this contract does not. Keeping the row DOM-free is
 * what makes "no audiences -> no row" provable in plain `node` (see
 * test/audiences.test.mjs) — and that is the one guarantee a host cannot
 * check on our behalf.
 */

/* Local copy of the panel's escape helper. The widget's own `esc` lives inside
   the IIFE and is not importable; duplicating four replacements is the cheaper
   half of that trade — the alternative is exporting widget internals just so
   this file can borrow them. */
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, (m) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[m]));
}

/**
 * Markup for the audience row, or '' when the host passed none.
 *
 * It used to reuse the `.tabs`/`.tab` vocabulary of the Open/Closed row. That
 * was wrong, and a screenshot settled it: two identical pairs of pills, one
 * above the other, and no way to tell which pair was the audience. Audience
 * and filter are different KINDS of choice — one says whose comments these
 * are, the other which of them to show — so they must not look alike.
 *
 * The row now sits in the panel head and is deliberately ASYMMETRIC: only the
 * active audience shows its name, the others are bare icons. That is what
 * makes the current state unmissable in a header-sized strip — there is always
 * exactly one name on screen, and it is the one in force. The look lives in
 * the widget's stylesheet (`.head .aud`); this function only emits the hooks.
 *
 * `icon` is INJECTED rather than imported: the widget's icon renderer lives
 * inside its IIFE, and taking it as an argument is what keeps this module
 * DOM-free and testable in plain `node`. A host names an icon from the
 * widget's own set (`bot`, `team`, …); an unknown name renders as nothing,
 * never as an error.
 *
 * @param {Array<{id: string, label: string, active?: boolean, icon?: string}>} audiences
 * @param {(name: string, size?: number) => string} [icon] renderer; omitted → no icons
 * @returns {string} HTML, or '' — never a stray empty container.
 */
export function audiencesHTML(audiences, icon) {
  if (!Array.isArray(audiences) || !audiences.length) return '';
  const draw = typeof icon === 'function' ? icon : () => '';
  const tabs = audiences.map((a) => {
    const on = a && a.active ? ' active' : '';
    const label = esc(a && a.label);
    // Both `id` and `label` come from the host and land in markup, so both are
    // escaped: an unescaped quote in an id would break out of the attribute.
    //
    // `aria-label` and `data-tip` carry the full name on EVERY button, active
    // or not: the inactive one is icon-only by design, and an icon with no
    // accessible name is a button nobody can identify — by screen reader or by
    // hovering. The visible `.aud-t` is decoration on top of that name, not
    // the name itself.
    //
    // That class is `.aud-t` and NOT the widget's own `.lbl`, even though
    // `.lbl` is what a label class would normally be called here: the pull
    // handle already wears `hlabel lbl`, and the widget used to grab it with
    // a bare `querySelector('.lbl')`. Sharing the name would have made that
    // lookup depend on markup ORDER — the handle happens to come first, so
    // nothing broke, but move it below the panel and 'Comment'/'Stop' starts
    // overwriting the audience name. A distinct class removes the question;
    // the lookup was tightened to `.hlabel` in the same change.
    return `<button class="aud${on}" data-aud="${esc(a && a.id)}"`
      + ` aria-pressed="${a && a.active ? 'true' : 'false'}"`
      + ` aria-label="${label}" data-tip="${label}">`
      + `${draw(a && a.icon, 14)}<span class="aud-t">${label}</span></button>`;
  }).join('');
  return `<div class="auds" role="group">${tabs}</div>`;
}

/**
 * Tell the host about a choice, and survive a host that throws.
 *
 * The row is the reviewer's only way back to the other audience, so a host
 * callback that blows up must cost nothing more than that one click: an
 * exception escaping here would abort the handler and leave the row dead.
 *
 * @returns {boolean} whether the host was reached — for tests, not for the UI.
 */
export function notifyAudience(onAudience, id) {
  if (typeof onAudience !== 'function') return false;
  try {
    onAudience(id);
    return true;
  } catch (e) {
    return false;
  }
}

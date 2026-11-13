import assert from 'node:assert';
import { audiencesHTML, notifyAudience } from '../src/audiences.js';

// ── The load-bearing half: no audiences means no row at all. ────────────────
// A host that never heard of audiences must get byte-for-byte the panel it
// got before. This is what keeps comment-layer usable standalone: the widget
// knows "here is a set of audiences, here is how to report a choice" and
// nothing about the host's channels.
{
  assert.equal(audiencesHTML(undefined), '', 'missing → no row');
  assert.equal(audiencesHTML(null), '', 'null → no row');
  assert.equal(audiencesHTML([]), '', 'empty → no row');
  assert.equal(audiencesHTML('local,project'), '', 'not an array → no row');
  assert.equal(audiencesHTML({ id: 'local' }), '', 'object → no row');
}

// ── One button per audience, the active one marked. ─────────────────────────
{
  const h = audiencesHTML([
    { id: 'local', label: 'Claude', active: true },
    { id: 'project', label: 'Team' },
  ]);
  assert.equal((h.match(/<button/g) || []).length, 2, 'one button per audience');
  assert.ok(/data-aud="local"/.test(h), 'id travels in data-aud');
  assert.ok(/data-aud="project"/.test(h), 'id travels in data-aud');
  assert.ok(/>Claude</.test(h) && />Team</.test(h), 'labels are rendered');
  assert.ok(/class="aud active" data-aud="local"/.test(h),
    'active audience carries the active class');
  assert.ok(/class="aud" data-aud="project"/.test(h),
    'inactive audience must not carry it');
  // NOT `.tabs`. The row used to borrow that class and became visually
  // indistinguishable from the Open/Closed filter below it — two identical
  // pairs of pills, no way to tell which was the audience.
  assert.ok(/class="auds"/.test(h) && !/class="tabs/.test(h),
    'the row must not borrow the filter row styling');
  assert.ok(/aria-pressed="true"/.test(h) && /aria-pressed="false"/.test(h),
    'pressed state is exposed, not only painted');
}

// ── Every button carries its name, active or not. ───────────────────────────
// The inactive audience is icon-only BY DESIGN, which is exactly why the name
// has to live in `aria-label`/`data-tip` on every button: an icon with no
// accessible name is a control nobody can identify, by screen reader or by
// hovering. Lose this and the asymmetry stops being a design and becomes a bug.
{
  const h = audiencesHTML([
    { id: 'local', label: 'Claude', active: true, icon: 'bot' },
    { id: 'project', label: 'Team', icon: 'team' },
  ]);
  assert.equal((h.match(/aria-label="Claude"/g) || []).length, 1);
  assert.equal((h.match(/aria-label="Team"/g) || []).length, 1);
  assert.equal((h.match(/data-tip="/g) || []).length, 2, 'both get a tooltip');
  // The visible label is a span so the stylesheet can show it only on the
  // active one; the markup itself always ships both.
  assert.equal((h.match(/<span class="aud-t">/g) || []).length, 2);
  // NOT `.lbl`: the panel's pull-handle already wears `hlabel lbl`, and the
  // widget looks it up by class. Sharing the name would make that lookup
  // depend on markup order.
  assert.ok(!/class="lbl"/.test(h), 'must not borrow the handle label class');
}

// ── Icons are injected, never imported, and never required. ─────────────────
// The widget's renderer lives inside its IIFE; taking it as an argument is
// what keeps this module DOM-free. A host that passes no renderer still gets
// a working row — icons are decoration, names are not.
{
  const calls = [];
  const stub = (name, size) => { calls.push([name, size]); return `<svg data-i="${name}"/>`; };
  const h = audiencesHTML([{ id: 'local', label: 'Claude', active: true, icon: 'bot' }], stub);
  assert.deepEqual(calls, [['bot', 14]], 'name and size reach the renderer');
  assert.ok(/data-i="bot"/.test(h), 'rendered icon is inlined');

  const bare = audiencesHTML([{ id: 'local', label: 'Claude', active: true }]);
  assert.ok(/aria-label="Claude"/.test(bare), 'no renderer → row still names itself');
  assert.ok(!/undefined/.test(bare), 'a missing icon must not leak "undefined"');

  const broken = audiencesHTML([{ id: 'local', label: 'Claude', icon: 'nope' }],
    () => '');
  assert.ok(/aria-label="Claude"/.test(broken), 'unknown icon renders as nothing, not an error');
}

// ── The row never navigates on its own. ─────────────────────────────────────
// Navigation belongs to the host: it owns the channel state and the label it
// shows elsewhere. If this markup could navigate, the choice would live in two
// places and the two would drift apart.
{
  const h = audiencesHTML([{ id: 'local', label: 'Claude', active: true }]);
  assert.ok(!/<a\b/.test(h), 'no anchors');
  assert.ok(!/href=/.test(h), 'no href');
  assert.ok(!/on(click|change)=/.test(h), 'no inline handlers');
}

// ── Host-supplied text is escaped, id included. ─────────────────────────────
// `label` and `id` come from whoever calls init(); both are interpolated into
// markup, so an unescaped quote in an id would break out of the attribute.
{
  const h = audiencesHTML([
    { id: 'a"><script>x</script>', label: '<b>bold</b> & "quoted"' },
  ]);
  assert.ok(!/<script>/.test(h), 'id cannot break out of the attribute');
  assert.ok(!/<b>/.test(h), 'label cannot inject markup');
  assert.ok(h.includes('&amp;'), 'ampersand escaped');
  assert.ok(h.includes('&quot;'), 'quotes escaped');
}

// ── A single audience still draws (one channel is a legitimate state). ──────
{
  const h = audiencesHTML([{ id: 'only', label: 'Only', active: true }]);
  assert.equal((h.match(/<button/g) || []).length, 1);
}

// ── notifyAudience: the host callback can never take the panel down. ────────
{
  const seen = [];
  assert.equal(notifyAudience((id) => seen.push(id), 'project'), true);
  assert.deepEqual(seen, ['project'], 'callback gets the id');

  assert.equal(notifyAudience(() => { throw new Error('host blew up'); }, 'x'),
    false, 'a throwing host is reported, not rethrown');
  assert.equal(notifyAudience(undefined, 'x'), false, 'no callback is safe');
  assert.equal(notifyAudience({}, 'x'), false, 'non-function is safe');
}

console.log('audiences: OK');

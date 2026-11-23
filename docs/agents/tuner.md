# Tuner
Designer's tweaks from the inspector as a change request: read, apply, clear.

The designer turns values (size, spacing, fill, text) live in the inspector. The canvas writes nothing to the mockup: it
saves the tweaks as a package of recommendations in the task, and applying them to the code is your job. Every call acts on
one task: send the header `X-Canvas-Task: <task-id>` (or the `/t/<task-id>` prefix); without it, on the current task.

## Read

    GET http://127.0.0.1:8765/api/tuner

`{"package": {…}, "rev": "…"}`; `package` is `null` when there is none. The package describes itself: its `instructions`
list explains every field, so read them. In short:

- `status` is `draft` (the designer is still tuning; the package is saved after every knob turn, do not act yet) or `ready`
  (they pressed «Send to AI»: this is the package they mean). Any later tweak flips it back to `draft`.
- `elements` hold the tweaked elements: `page`, `selector`, `label`, `trail`, `text` and `edits`. Find the element by the
  agreement of these signals, not by `selector` alone.
- an edit has `prop` (CSS property), `from` (what the browser showed), `to` (what the designer set, a free value, not a
  token), `rule` (the selector of the rule that won the cascade, that is where to edit; `[style]` is the inline style, `null`
  means find the source yourself), `verdict` (where the old value came from) and `hint` (design-system tokens that match the
  old value).
- `tier: "used"` in a hint is a fact; `tier: "shape"` is a guess: ask the designer before applying it. With `snap` the
  designer chose a token: write `var(<snap.token>)` at `rule`, not the literal in `to`.
- `note` is the designer's own text, `ds` names the design system the verdicts were checked against.

## Clear

    POST http://127.0.0.1:8765/api/tuner {"action": "clear"}

After you have applied the package, clear it with this one request (answer `{"ok": true, "cleared": true}`). Do not edit or
empty `.dc-tuner.json` by hand: the open canvas picks the change up only through the server, and a stale `ready` left behind
reads as «still waiting for Claude». The canvas itself writes the package with a `base_rev` of the `rev` it read and gets
`409` when the file changed; you do not need to write a package.

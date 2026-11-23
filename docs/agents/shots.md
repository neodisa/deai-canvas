# Screenshots
Screenshots of an iteration's pages: take, stop, progress, manifest.

The canvas keeps a frame (`.webp`) of every page and state of an iteration in `iterations/<itN>/shots/`, with a manifest
`shots/manifest.json`. They are made by a headless Chromium driven by Node and Playwright (see `SETUP.md` in `<deai>`).
Every call acts on one task: send the header `X-Canvas-Task: <task-id>` (or the `/t/<task-id>` prefix); without it, on the
current task. Every `it` is an iteration id such as `it3`; a bad one is `400`.

## Take

    POST http://127.0.0.1:8765/api/shoot {"it": "itN"}
    POST http://127.0.0.1:8765/api/shoot {"it": "itN", "all": true, "vp": 375, "motion": false, "only": ["<frame key>"]}

Only `it` is required. By default only frames that are out of date are re-shot; `all: true` re-shoots every frame. `only` is
a list of frame keys (an unknown key stops the run). `vp` is the width in pixels, an integer from 240 to 3840 (default 1280;
frames of different widths live side by side). Pages are shot with `prefers-reduced-motion: reduce`; `motion: true` keeps the
animation. `check: true` opens no browser: it only recomputes which frames are out of date and updates the manifest.

The call answers when the run ends (the limit is 15 minutes), so poll the progress meanwhile. Answers:

- `{"ok": true, "report": {"vp", "shot", "failed", "problems", "left"}, "stderr"}`: `ok` means the run finished; look at
  `report.failed` too, some frames can fail while the others are saved. `left` lists frames not re-shot.
- `{"ok": true, "already": true, "progress": {…}}`: a run of this iteration is going, you joined it.
- `{"ok": true, "stopped": true, "progress": {…}}`: someone stopped it; the frames already saved stay.
- `{"ok": false, "error"}`: no Node, no Chromium for Playwright, did not fit in 15 minutes, and so on.

## Progress and stop

    GET  http://127.0.0.1:8765/api/shoot-progress?it=itN
    POST http://127.0.0.1:8765/api/shoot-stop {"it": "itN"}

Progress is `{"running", "total", "done", "current", "frames", "failed", "stopped"}`; with no run `running` is `false`
(not `404`). `shoot-stop` ends the run of that iteration: `{"ok": true, "stopped": true}`, or `"stopped": false` when
nothing was running.

## Manifest

    GET http://127.0.0.1:8765/api/shots?it=itN

`{"it", "checkedAt", "shots": {"<frame key>": {…}}}`; with no manifest `shots` is empty. A frame entry carries its size, the
time it was taken, its `stamp` (a hash of the mockup it was taken from), `stale` (the mockup changed after the shot) and
`stable` (`false`: the page kept moving while it was shot, do not trust the frame). Frame keys are the page ids; a state of a flow
node is `<page>~<hash>`, and a width other than 1280 adds `@<width>`.

# Deai Canvas landing page

The public site at https://neodisa.github.io/deai-canvas/. It is static and uses relative paths.
`.github/workflows/pages.yml` publishes it on every push to `main` that touches `landing/` and after every release.

Local preview from the repository root:

```sh
python3 -m http.server 8080 --bind 127.0.0.1 --directory landing
```

`python3 -B ops/build_site.py --src landing --out <new folder>` builds exactly what Pages serves: these files without this
README, with the newest release tag `vX.Y.Z` written into the footer.

## Editing

The page is designed and reviewed as a Deai Canvas task: comments are pinned on an iteration and an agent makes the next one.
Copy the approved iteration over `landing/` and commit it. Nothing syncs back from the repository to the task.

## Product screenshots

The site uses 2880 px WebP captures in `assets/`; the lightbox opens the same files. Northline (rail booking) and Forma (store
checkout) are fictional. The captures use the actual Deai Canvas UI and locally seeded project data.

To recapture the six screenshots, install the repo's Playwright dependency and Chromium, and have `python3` and `cwebp` on your
path. Then run this from the repository root:

```sh
node ops/landing-shots.mjs
```

The capture script uses a temporary Deai Canvas space and a loopback server. It builds the team preview with the local static
publishing module. The fixtures are in `ops/landing-shots/`.

`node ops/landing-og.mjs` renders the link preview `assets/og.png` (1200×630).

## Demo photography

Only the photographs inside the two fictional projects were generated with an image model. The landing page depicts the rendered
prototypes inside real Deai Canvas captures. The prompts:

**Northline** (`ops/landing-shots/northline-rail.webp`)

> Use case: photorealistic-natural. Asset type: wide photo header inside a fictional European rail booking prototype, Northline. An exceptional editorial travel photograph, panoramic 3:2 frame composed to also crop to a wide 3.5:1 ribbon through the middle: a single small red passenger train winding from left toward center along a Swiss Alpine valley, looking slightly down from the opposite grassy hillside. Folded emerald and olive slopes, pale limestone mountain faces in the distance, a few faraway dark trees, fine film grain, clean natural midmorning light. The train is sharp enough to recognize at small size. Darker uncluttered hillside on the left for separate white website text to be placed later. Authentic medium-format travel editorial, richly colored and tactile, no text, no logos, no graphic design or UI.

**Forma** (`ops/landing-shots/forma-chair.webp`)

> Use case: product-mockup. Asset type: product catalogue photo inside a fictional premium furniture checkout prototype, Forma. A beautiful single caramel brown gently curved upholstered lounge chair on a slender brushed chrome tubular base, in the language of independently designed European modern furniture. Three-quarter angle showing the inviting front and side, centered cleanly on a plain warm grey plaster cyclorama with generous breathing room. Natural sidelight, crisp honest texture, subtle shadow, boutique furniture catalogue editorial, square framing, photographed with great restraint. Chair only, no person, no lettering, no logo, no website UI.

Rethink Sans is distributed under the [SIL Open Font License](assets/rethink-sans-OFL.txt).

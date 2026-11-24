"""Example Deai Canvas module: «Contrast» (Контраст).

No tool functions: all logic is in the panel (`panel/contrast.js`), which works with the mockup page through the core
helper `deai.page.*` (the tool declares `"page": [...]` in `module.json`). The file must exist: the module is a folder with
`module.json` and `server.py`. The only function is the required `check`.
"""


def check(ctx):
    """Health check required of every module. Nothing to verify: no files, no network."""
    return {"ok": True}

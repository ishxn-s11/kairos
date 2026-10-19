"""Bundle the multi-file frontend into one self-contained site.html.

Reads frontend/index.html, inlines assets/css/main.css, all assets/js/*.js,
and converts assets/audio/ambience.wav to a base64 data URI so the single
file previews/deploys anywhere. Run:  python3 frontend/build.py
"""

import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def inline() -> str:
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    # CSS
    css = (ROOT / "assets/css/main.css").read_text(encoding="utf-8")
    html = re.sub(
        r'<link rel="stylesheet" href="assets/css/main\.css(?:\?v=\d+)?" */?>',
        lambda m: "<style>\n" + css + "\n</style>",
        html,
    )

    # JS
    def js_repl(m: re.Match) -> str:
        # strip the ?v= cache token before resolving to a file
        src = m.group(1).split("?", 1)[0]
        code = (ROOT / src).read_text(encoding="utf-8")
        return "<script>\n" + code + "\n</script>"

    html = re.sub(r'<script src="(assets/js/[^"]+)"></script>', js_repl, html)

    # Audio -> data URI
    wav = (ROOT / "assets/audio/ambience.wav").read_bytes()
    uri = "data:audio/wav;base64," + base64.b64encode(wav).decode("ascii")
    html = re.sub(
        r'<source src="assets/audio/ambience\.wav" type="audio/wav" */?>',
        lambda m: f'<source src="{uri}" type="audio/wav" />',
        html,
    )

    # Remove Google Fonts link (offline-safe); mono falls back to system stack.
    html = html.replace(
        '<link rel="preconnect" href="https://fonts.googleapis.com" />\n', ""
    )
    html = re.sub(
        r'<link href="https://fonts\.googleapis\.com[^"]*" rel="stylesheet" */?>\n?', "", html
    )
    return html


if __name__ == "__main__":
    out = inline()
    (ROOT / "site.html").write_text(out, encoding="utf-8")
    print("site.html", len(out), "chars")

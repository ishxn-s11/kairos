#!/usr/bin/env python3
"""Parity guard: the static frontend and the Next.js port must not drift apart.

The showcase ships two frontends over one set of shared material: a multi-page
static site in ``frontend/`` and a React/Next.js port in ``frontend-next/``. The
port is not a rewrite — it re-uses the same stylesheet, the same artwork/data
files and the same logic, wrapped for ES modules. Because both copies are edited
by hand they drift silently, and every bug this guard exists for was found by
accident in a browser first:

* ``.pull-ghost`` CSS lived in ``main.css`` but had never been copied into the
  Next stylesheet, so pulled card artwork rendered unstyled.
* ``initCardPulls`` was exported from the Next client but never imported by the
  Next home page, so the drag-to-open gesture was dead code there.
* A transform injected the static ``const D = window.Decisions;`` into the ES
  copy, shadowing the module import and killing the whole explorer.
* CRLF vs LF endings made a mirror script's exact-match assertion fail.

Four levels of checking, because the two copies are not identical by nature:

``byte twins``
    Pure assets (stylesheet, manifest, output.csv, baseline.json). Must match
    byte for byte — no wrapper, no excuse.

``tree twins``
    Mirrored directories (the image set), compared by file name and contents,
    flagging extra *and* missing files.

``mirror twins``
    Logic that was copied verbatim: the only sanctioned differences are the
    module wrapper, comments, whitespace, line endings and ``assets/`` vs
    ``/assets/`` paths. Compared on both their normalised body and their
    exported surface.

``adapted twins``
    Ports that deliberately restructured their API (a renamed loader, a
    different base-URL resolution, two static modules merged into one Next
    module). Their bodies are not comparable, so the guard asserts the *shared
    vocabulary*: every domain string in one copy must appear in the other unless
    the manifest explicitly sanctions the difference. Anything new is drift.

Usage:
    python3 code/tools/check_parity.py            # report + exit 1 on drift
    python3 code/tools/check_parity.py --list     # print the manifest and exit
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #

#: Pure assets: byte-for-byte identical. One differing byte is drift.
BYTE_TWINS: list[tuple[str, str]] = [
    ("frontend/assets/css/main.css", "frontend-next/app/globals.css"),
    ("frontend/assets/img/manifest.json", "frontend-next/public/assets/img/manifest.json"),
    ("frontend/output.csv", "frontend-next/public/output.csv"),
    ("frontend/baseline.json", "frontend-next/public/baseline.json"),
]

#: Whole directories mirrored by file name (the image set the asset system
#: resolves). Extra or missing files count as drift in both directions.
TREE_TWINS: list[tuple[str, str]] = [
    ("frontend/assets/img", "frontend-next/public/assets/img"),
]


@dataclass(frozen=True)
class MirrorTwin:
    """Logic copied verbatim between the two frontends."""

    static: tuple[str, ...]
    next: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class AdaptedTwin:
    """A port that restructured its public API, checked on shared vocabulary.

    ``sanctioned`` lists vocabulary the static copy has and the port does not
    (or vice versa, via ``sanctioned_next``), each with the reason. New
    vocabulary that is not listed here fails the guard: that is the drift case.
    """

    static: tuple[str, ...]
    next: tuple[str, ...]
    note: str = ""
    sanctioned_static_only: dict[str, str] = field(default_factory=dict)
    sanctioned_next_only: dict[str, str] = field(default_factory=dict)


#: Logic copied verbatim: normalised bodies must match.
MIRROR_TWINS: list[MirrorTwin] = [
    MirrorTwin(
        static=("frontend/assets/js/art.js",),
        next=("frontend-next/lib/art.js",),
        note="generative artwork + SVG slide builders",
    ),
    MirrorTwin(
        static=("frontend/assets/js/data.js",),
        next=("frontend-next/lib/data.js",),
        note="stage copy, about sections, cloud words",
    ),
    MirrorTwin(
        static=("frontend/assets/js/evidence.js",),
        next=("frontend-next/lib/evidence.js",),
        note="evidence image registry",
    ),
    MirrorTwin(
        static=("frontend/assets/js/decisions-ui.js",),
        next=("frontend-next/lib/decisions-ui-shared.js",),
        note="decision explorer renderer (cards, sparklines, detail)",
    ),
]

#: Ports that restructured their API; checked on shared vocabulary.
ADAPTED_TWINS: list[AdaptedTwin] = [
    AdaptedTwin(
        static=("frontend/assets/js/decisions.js",),
        next=("frontend-next/lib/decisions.js",),
        note="output.csv loader + CSV/plan parsers",
        sanctioned_static_only={
            "output.csv fetch failed: ": "static loader throws with the HTTP status",
            "status": "the port moved per-status/per-method counting out of the "
                      "loader, so the field names are no longer string literals here",
            "method": "see 'status' — counting moved out of the loader",
        },
    ),
    AdaptedTwin(
        static=("frontend/assets/js/live-api.js",),
        next=("frontend-next/lib/live-api.js",),
        note="live engine client",
    ),
    AdaptedTwin(
        static=(
            "frontend/assets/js/transitions.js",
            "frontend/assets/js/common.js",
            "frontend/assets/js/assets.js",
        ),
        next=("frontend-next/lib/client.js",),
        note="page transitions + chrome + asset loader (three static modules "
        "merged into one Next module)",
        sanctioned_static_only={
            "about.html": "static routes are file names; the port uses /about/ etc.",
            "mailto:": "the port renders contact links as JSX, not in this module",
            "_blank": "the port renders external links as JSX, not in this module",
        },
        sanctioned_next_only={
            "undefined": "typeof-guard for SSR-safe module scope, which the "
                         "browser-only static module does not need",
        },
    ),
]

# --------------------------------------------------------------------------- #
# A small string-aware JavaScript scanner
# --------------------------------------------------------------------------- #


def _regex_allowed(prev_sig: str) -> bool:
    """Whether ``/`` starts a regex literal rather than being division.

    Standard heuristic: a slash begins a regex unless the previous significant
    character could end an expression. Without this, ``/[&<>"]/g`` — a character
    class containing a quote — is read as a string opener and the scanner
    desynchronises for the rest of the file, which silently disabled comment
    stripping and manufactured phantom drift.
    """
    if not prev_sig:
        return True
    if prev_sig.isalnum() or prev_sig in "_$)]\"'`":
        return False
    return True


def scan_js(src: str) -> tuple[str, list[str]]:
    """Strip JS comments and collect string literals in one pass.

    String-aware (single/double quotes, template literals, escapes) and
    regex-literal aware (character classes included). Block comments keep their
    newlines so the stripped source stays line-aligned with the original.
    Returns ``(stripped_source, literals)``.
    """
    out: list[str] = []
    literals: list[str] = []
    buf: list[str] | None = None
    i, n = 0, len(src)
    state: str | None = None  # None | "'" | '"' | '`' | "line" | "block"
    prev_sig = ""

    def emit(ch: str) -> None:
        nonlocal prev_sig
        out.append(ch)
        if buf is not None:
            buf.append(ch)
        if ch and not ch.isspace():
            prev_sig = ch

    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if state is None:
            if c == "/" and nxt == "/":
                state = "line"
                i += 2
                continue
            if c == "/" and nxt == "*":
                state = "block"
                i += 2
                continue
            if c == "/" and _regex_allowed(prev_sig):
                emit(c)
                i += 1
                in_class = False
                while i < n:
                    ch = src[i]
                    if ch == "\\":
                        emit(ch)
                        if i + 1 < n:
                            emit(src[i + 1])
                            i += 2
                            continue
                        i += 1
                        continue
                    if ch == "\n":  # unterminated regex — stop scanning it
                        break
                    emit(ch)
                    if ch == "[":
                        in_class = True
                    elif ch == "]":
                        in_class = False
                    elif ch == "/" and not in_class:
                        i += 1
                        break
                    i += 1
                continue
            if c in "\"'`":
                state = c
                buf = []
                emit(c)
                i += 1
                continue
            emit(c)
            i += 1
            continue
        if state == "line":
            if c == "\n":
                state = None
                emit(c)
            i += 1
            continue
        if state == "block":
            if c == "*" and nxt == "/":
                state = None
                i += 2
                continue
            if c == "\n":
                out.append(c)
            i += 1
            continue
        # inside a string / template literal
        if c == "\\":
            emit(c)
            if i + 1 < n:
                emit(src[i + 1])
                i += 2
                continue
            i += 1
            continue
        emit(c)
        if c == state:
            if buf is not None:
                literals.append("".join(buf[1:-1]))
                buf = None
            state = None
        i += 1
    return "".join(out), literals


def strip_js_comments(src: str) -> str:
    return scan_js(src)[0]


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #

#: Lines that are pure module-wrapper syntax: they differ by construction
#: between the IIFE/global copy and the ES-module copy.
_DROP_LINE: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\(\(\)\s*=>\s*\{$"),
    re.compile(r"^\}\)\(\);$"),
    re.compile(r"^window\.[A-Za-z_$][\w$]*\s*=\s*\(\(\)\s*=>\s*\{$"),
    re.compile(r"^(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*\(\(\)\s*=>\s*\{$"),
    re.compile(r"^export\s+default\b.*$"),
    re.compile(r"^import\b.*$"),
    re.compile(r"^return\s+window\.[A-Za-z_$][\w$]*;$"),
    # aggregate hand-outs — checked separately as the exported surface, so they
    # are removed from the body comparison on both sides
    re.compile(r"^window\.[A-Za-z_$][\w$]*\s*=\s*\{[^{}]*\};?$"),
    re.compile(r"^return\s*\{[^{}]*\};$"),
    # the data-loader shim that only exists to bridge the two module styles
    re.compile(r"^const\s+D\s*=\s*(?:window\.Decisions|\{.*\});$"),
)

#: Wrapper syntax around a *named* declaration: rewrite to the bare form so both
#: copies line up (``export const STATUSES = [...]`` -> ``const STATUSES = [...]``).
_REWRITE_LINE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^export\s+const\s+([A-Za-z_$][\w$]*)\s*="), r"const \1 ="),
    (re.compile(r"^export\s+let\s+([A-Za-z_$][\w$]*)\s*="), r"let \1 ="),
    (re.compile(r"^export\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("), r"function \1("),
)

#: ``window.EVIDENCE = [`` and ``export const EVIDENCE = [`` are the same thing.
_REWRITE_ARRAY = re.compile(r"^window\.([A-Za-z_$][\w$]*)\s*=\s*(\[.*)$")


def normalize_js(src: str) -> str:
    """Reduce a mirrored module to a wrapper- and formatting-insensitive form."""
    src = src.replace("\r\n", "\n").replace("\r", "\n")
    src = strip_js_comments(src)
    # the only sanctioned path difference: document-relative vs root-absolute
    src = src.replace('"/assets/', '"assets/').replace("'/assets/", "'assets/")

    lines: list[str] = []
    for raw in src.split("\n"):
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if any(p.match(line) for p in _DROP_LINE):
            continue
        arr = _REWRITE_ARRAY.match(line)
        if arr:
            line = f"const {arr.group(1)} = {arr.group(2)}"
        else:
            for pat, repl in _REWRITE_LINE:
                if pat.match(line):
                    line = pat.sub(repl, line)
                    break
        lines.append(line)
    return "\n".join(lines)


def exported_surface(src: str) -> set[str]:
    """Names a consumer of this module can reach, across both wrapper styles.

    ``export default ART`` is deliberately *not* counted: the default binding's
    local name is an implementation detail, and the aggregate object it hands
    out is already expanded below.
    """
    src = strip_js_comments(src)
    names: set[str] = set()
    for m in re.finditer(r"^export\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", src, re.M):
        names.add(m.group(1))
    for m in re.finditer(r"^export\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)", src, re.M):
        names.add(m.group(1))
    for m in re.finditer(r"^export\s*\{([^}]*)\}", src, re.M):
        for part in m.group(1).split(","):
            name = part.split(" as ")[-1].strip()
            if name:
                names.add(name)
    # aggregate hand-out objects: window.X = { a, b } and return { a, b }
    for m in re.finditer(r"window\.[A-Za-z_$][\w$]*\s*=\s*\{([^}]*)\}", src):
        names.update(_names_in(m.group(1)))
    for m in re.finditer(r"^\s*return\s*\{([^}]*)\}", src, re.M):
        names.update(_names_in(m.group(1)))
    # array hand-outs: window.EVIDENCE = [ ... ] exposes the binding itself
    for m in re.finditer(r"window\.([A-Za-z_$][\w$]*)\s*=\s*\[", src):
        names.add(m.group(1))
    return names


def _names_in(inner: str) -> set[str]:
    return {
        part.strip()
        for part in inner.split(",")
        if re.fullmatch(r"[A-Za-z_$][\w$]*", part.strip())
    }


#: Vocabulary-shaped literals: short, identifier-ish strings that name domain
#: facts (statuses, methods, class names, endpoints, commands). Long prose and
#: HTML fragments are excluded — they legitimately differ between the copies.
_VOCAB = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-:/ ]{2,59}$")


def shared_vocabulary(src: str) -> set[str]:
    """Domain strings the two copies are expected to agree on."""
    _, literals = scan_js(src.replace("\r\n", "\n").replace("\r", "\n"))
    vocab: set[str] = set()
    for lit in literals:
        s = re.sub(r"\s+", " ", lit).strip()
        if not s or "\n" in lit:
            continue
        if not _VOCAB.match(s):
            continue
        # ignore pure paths/fragments and template interpolation noise
        strip_and_fold = s.replace("/assets/", "assets/").lstrip("/")
        if strip_and_fold != s and s.startswith("/assets/"):
            s = strip_and_fold
        vocab.add(s)
    return vocab


# --------------------------------------------------------------------------- #
# Comparisons
# --------------------------------------------------------------------------- #


@dataclass
class Finding:
    kind: str  # byte | tree | missing | body | surface | vocabulary
    left: str
    right: str = ""
    detail: str = ""
    diff: str = ""


@dataclass
class Result:
    checked: int = 0
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _norm_text(path: Path) -> str:
    text = _read(path).replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)


def check_byte_twins(
    res: Result, twins: Sequence[tuple[str, str]] | None = None
) -> None:
    for left_rel, right_rel in twins if twins is not None else BYTE_TWINS:
        left, right = REPO_ROOT / left_rel, REPO_ROOT / right_rel
        res.checked += 1
        if not left.exists() or not right.exists():
            missing = [p for p in (left_rel, right_rel) if not (REPO_ROOT / p).exists()]
            res.findings.append(
                Finding("missing", left_rel, right_rel, "missing file(s): " + ", ".join(missing))
            )
            continue
        lb, rb = left.read_bytes(), right.read_bytes()
        if lb != rb:
            diff = "\n".join(
                difflib.unified_diff(
                    _norm_text(left).split("\n"),
                    _norm_text(right).split("\n"),
                    fromfile=left_rel,
                    tofile=right_rel,
                    lineterm="",
                    n=2,
                )
            )
            res.findings.append(
                Finding(
                    "byte", left_rel, right_rel,
                    f"{len(lb)} vs {len(rb)} bytes — this file must match byte for byte",
                    diff[:4000],
                )
            )


def check_tree_twins(
    res: Result, twins: Sequence[tuple[str, str]] | None = None
) -> None:
    for left_rel, right_rel in twins if twins is not None else TREE_TWINS:
        left, right = REPO_ROOT / left_rel, REPO_ROOT / right_rel
        if not left.is_dir() or not right.is_dir():
            res.findings.append(
                Finding("missing", left_rel, right_rel, "mirrored directory is missing")
            )
            continue
        lf = {p.name: p for p in left.iterdir() if p.is_file()}
        rf = {p.name: p for p in right.iterdir() if p.is_file()}
        for name in sorted(set(lf) | set(rf)):
            res.checked += 1
            if name not in lf:
                res.findings.append(
                    Finding("tree", f"{left_rel}/{name}", f"{right_rel}/{name}",
                            "present in the Next port but missing from the static site")
                )
            elif name not in rf:
                res.findings.append(
                    Finding("tree", f"{left_rel}/{name}", f"{right_rel}/{name}",
                            "present in the static site but missing from the Next port")
                )
            elif lf[name].read_bytes() != rf[name].read_bytes():
                res.findings.append(
                    Finding("tree", f"{left_rel}/{name}", f"{right_rel}/{name}",
                            "file contents differ")
                )


def _label(static: Sequence[str], nxt: Sequence[str]) -> str:
    return (
        " + ".join(Path(p).name for p in static)
        + " <-> "
        + " + ".join(Path(p).name for p in nxt)
    )


def check_mirror_twins(
    res: Result, twins: Sequence[MirrorTwin] | None = None
) -> None:
    for twin in twins if twins is not None else MIRROR_TWINS:
        label = _label(twin.static, twin.next)
        left_paths = [REPO_ROOT / p for p in twin.static]
        right_paths = [REPO_ROOT / p for p in twin.next]
        absent = [str(p) for p in (*left_paths, *right_paths) if not p.exists()]
        res.checked += 1
        if absent:
            res.findings.append(
                Finding("missing", label, twin.note, "missing file(s): " + ", ".join(absent))
            )
            continue

        left_src = "\n".join(_read(p) for p in left_paths)
        right_src = "\n".join(_read(p) for p in right_paths)

        ls, rs = exported_surface(left_src), exported_surface(right_src)
        if ls != rs:
            res.findings.append(
                Finding(
                    "surface", label, twin.note,
                    "exported surface differs — "
                    f"static only: {', '.join(sorted(ls - rs)) or '—'}; "
                    f"next only: {', '.join(sorted(rs - ls)) or '—'}",
                )
            )

        ln, rn = normalize_js(left_src), normalize_js(right_src)
        if ln != rn:
            diff = "\n".join(
                difflib.unified_diff(
                    ln.split("\n"), rn.split("\n"),
                    fromfile=label + " [static]",
                    tofile=label + " [next]",
                    lineterm="", n=2,
                )
            )
            res.findings.append(
                Finding(
                    "body", label, twin.note,
                    f"normalised bodies differ ({_digest(ln)} vs {_digest(rn)}) — "
                    "one side changed without the other",
                    diff[:4000],
                )
            )


def check_adapted_twins(
    res: Result, twins: Sequence[AdaptedTwin] | None = None
) -> None:
    for twin in twins if twins is not None else ADAPTED_TWINS:
        label = _label(twin.static, twin.next)
        left_paths = [REPO_ROOT / p for p in twin.static]
        right_paths = [REPO_ROOT / p for p in twin.next]
        absent = [str(p) for p in (*left_paths, *right_paths) if not p.exists()]
        res.checked += 1
        if absent:
            res.findings.append(
                Finding("missing", label, twin.note, "missing file(s): " + ", ".join(absent))
            )
            continue

        left_vocab = shared_vocabulary("\n".join(_read(p) for p in left_paths))
        right_vocab = shared_vocabulary("\n".join(_read(p) for p in right_paths))

        unsanctioned_left = left_vocab - right_vocab - set(twin.sanctioned_static_only)
        unsanctioned_right = right_vocab - left_vocab - set(twin.sanctioned_next_only)
        if unsanctioned_left or unsanctioned_right:
            parts = []
            if unsanctioned_left:
                parts.append("static only: " + ", ".join(repr(s) for s in sorted(unsanctioned_left)))
            if unsanctioned_right:
                parts.append("next only: " + ", ".join(repr(s) for s in sorted(unsanctioned_right)))
            res.findings.append(
                Finding(
                    "vocabulary", label, twin.note,
                    "shared vocabulary drifted — " + "; ".join(parts)
                    + ". If the difference is deliberate, add it to the twin's "
                    "sanctioned sets in code/tools/check_parity.py.",
                )
            )

        res.notes.append(f"adapted (vocabulary-checked): {label} — {twin.note}")


def run_all() -> Result:
    res = Result()
    check_byte_twins(res)
    check_tree_twins(res)
    check_mirror_twins(res)
    check_adapted_twins(res)
    return res


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _utf8_stdout() -> None:
    """Console code pages (cp1252 on Windows) cannot print the box glyphs."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):  # pragma: no cover - odd stdio wrappers
        pass


def report(res: Result, show_manifest: bool = False) -> None:
    _utf8_stdout()
    if show_manifest:
        print("frontend parity guard — manifest")
        print("=" * 72)
        for left, right in BYTE_TWINS:
            print(f"  byte   {left}\n         == {right}")
        for left, right in TREE_TWINS:
            print(f"  tree   {left}/  ==  {right}/")
        for t in MIRROR_TWINS:
            print(f"  mirror [body+surface]  {' + '.join(t.static)}")
            print(f"                        -> {' + '.join(t.next)}")
        for t in ADAPTED_TWINS:
            print(f"  adapted [vocabulary]   {' + '.join(t.static)}")
            print(f"                        -> {' + '.join(t.next)}")
        print()

    if res.ok:
        print(f"OK — {res.checked} parity checks passed, no drift detected.")
        return

    print(f"DRIFT — {len(res.findings)} problem(s) across {res.checked} checks:\n")
    for i, f in enumerate(res.findings, 1):
        print(f"[{i}] {f.kind.upper()}: {f.left}")
        if f.right:
            print(f"    vs {f.right}")
        if f.detail:
            print(f"    {f.detail}")
        if f.diff:
            print("    " + "\n    ".join(f.diff.splitlines()))
        print()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="print the manifest and exit")
    parser.add_argument("--quiet", action="store_true", help="only print failures")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list:
        report(Result(), show_manifest=True)
        return 0

    res = run_all()
    if args.quiet and res.ok:
        return 0
    report(res)
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())

"""Tests for the frontend parity guard (code/tools/check_parity.py).

Run: python3 -m pytest code/tests -q

Two kinds of test live here:

* the guard against the real repository — it must report no drift, otherwise the
  static site and the Next.js port have diverged and one of them is stale;
* the guard against *injected* drift — a guard that cannot fail is worthless, so
  every tier is exercised with a deliberately broken fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CODE_DIR.parent
sys.path.insert(0, str(CODE_DIR / "tools"))

import check_parity as cp  # noqa: E402


# --------------------------------------------------------------------------- #
# The real repository
# --------------------------------------------------------------------------- #


def test_real_repository_has_no_drift() -> None:
    """This is the assertion that matters: both frontends ship in sync."""
    result = cp.run_all()
    assert result.checked > 0, "the guard checked nothing — the manifest is broken"
    assert result.ok, (
        "frontend drift detected:\n"
        + "\n".join(
            f"- [{f.kind}] {f.left}: {f.detail}" for f in result.findings
        )
    )


def test_manifest_covers_every_shared_surface() -> None:
    """The manifest must actually point at files that exist."""
    missing = []
    for left, right in cp.BYTE_TWINS:
        for rel in (left, right):
            if not (REPO_ROOT / rel).exists():
                missing.append(rel)
    for twin in cp.MIRROR_TWINS:
        for rel in (*twin.static, *twin.next):
            if not (REPO_ROOT / rel).exists():
                missing.append(rel)
    assert not missing, f"manifest references missing files: {missing}"


# --------------------------------------------------------------------------- #
# The JavaScript scanner (comment stripping / literal collection)
# --------------------------------------------------------------------------- #


def test_scanner_keeps_regex_class_containing_a_quote() -> None:
    """Regression: ``/[&<>"]/g`` used to desynchronise the scanner.

    Reading that ``"`` as a string opener made the scanner treat the rest of the
    file as string content, so comment stripping silently stopped and produced
    phantom drift.
    """
    src = 'const esc = (s) => s.replace(/[&<>"]/g, "x");\n/* real comment */\nconst after = 1;\n'
    stripped, literals = cp.scan_js(src)
    assert "real comment" not in stripped
    assert "const after = 1;" in stripped
    assert '"[&<>"]"' not in stripped  # the regex is code, not a literal
    assert "x" in literals


def test_scanner_ignores_comment_markers_inside_strings() -> None:
    src = 'const ns = "http://www.w3.org/2000/svg";/* gone */const b = "a//b";\n'
    stripped, literals = cp.scan_js(src)
    assert "http://www.w3.org/2000/svg" in stripped
    assert "a//b" in stripped
    assert "gone" not in stripped
    assert "http://www.w3.org/2000/svg" in literals


def test_scanner_preserves_template_literals_and_escapes() -> None:
    src = "const t = `line ${x} // not a comment`;\n// trailing\nconst u = 'it\\\\'s';\n"
    stripped, literals = cp.scan_js(src)
    assert "// not a comment" in stripped
    assert "trailing" not in stripped
    assert "const u =" in stripped
    assert any("line " in lit for lit in literals)


def test_scanner_does_not_mistake_division_for_a_regex() -> None:
    src = "const half = a / b;\n/* c */\nconst ok = 2 / 1;\n"
    stripped, _ = cp.scan_js(src)
    assert "const half = a / b;" in stripped
    assert "const ok = 2 / 1;" in stripped
    assert "/* c */" not in stripped


# --------------------------------------------------------------------------- #
# Normalisation: the two wrapper styles must collapse together
# --------------------------------------------------------------------------- #


def test_normalize_equates_iife_and_esm_wrappers() -> None:
    static = (
        "/* header */\n"
        "window.DATA = (() => {\n"
        '  const STATUSES = ["a", "b"];\n'
        "  function fmt(x) { return x; }\n"
        "  return { STATUSES, fmt };\n"
        "})();\n"
    )
    nxt = (
        "/* a different header */\n"
        'export const STATUSES = ["a", "b"];\n'
        "export function fmt(x) { return x; }\n"
    )
    assert cp.normalize_js(static) == cp.normalize_js(nxt)


def test_normalize_ignores_line_endings_and_asset_path_style() -> None:
    static = 'const E = [{ src: "assets/img/a.png" }];\r\n'
    nxt = 'export const E = [{ src: "/assets/img/a.png" }];\n'
    assert cp.normalize_js(static) == cp.normalize_js(nxt)


def test_normalize_still_detects_a_real_body_change() -> None:
    a = cp.normalize_js('() => {\n  const N = 1500;\n})();\n')
    b = cp.normalize_js('const f = () => {\n  const N = 1501;\n};\n')
    assert a != b


def test_normalize_still_detects_a_changed_string_literal() -> None:
    a = cp.normalize_js('window.X = (() => { const s = "affordable_now"; })();\n')
    b = cp.normalize_js('export const Y = () => { const s = "not_affordable"; };\n')
    assert a != b


# --------------------------------------------------------------------------- #
# Exported surface
# --------------------------------------------------------------------------- #


def test_exported_surface_agrees_across_wrapper_styles() -> None:
    static = '(() => {\n  function render() {}\n  window.DecisionUI = { render };\n})();\n'
    nxt = "export function render() {}\n"
    assert cp.exported_surface(static) == cp.exported_surface(nxt) == {"render"}


def test_exported_surface_flags_a_dropped_member() -> None:
    full = '(() => {\n  window.ART = { paint, MOTIFS, el };\n})();\n'
    missing = '(() => {\n  window.ART = { paint, MOTIFS };\n})();\n'
    diff = cp.exported_surface(full) - cp.exported_surface(missing)
    assert diff == {"el"}


def test_exported_surface_accepts_array_handouts() -> None:
    static = 'window.EVIDENCE = [\n  { id: "image_01" },\n];\n'
    nxt = 'export const EVIDENCE = [\n  { id: "image_01" },\n];\n'
    assert "EVIDENCE" in cp.exported_surface(static)
    assert cp.exported_surface(static) == cp.exported_surface(nxt)


# --------------------------------------------------------------------------- #
# Drift injection: every tier must be able to fail
# --------------------------------------------------------------------------- #


def _seed(root: Path, mapping: dict[str, str]) -> None:
    for rel, text in mapping.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def test_byte_twin_drift_is_detected(tmp_path, monkeypatch) -> None:
    left, right = cp.BYTE_TWINS[0]
    _seed(tmp_path, {left: "a { color: red; }\n", right: "a { color: red; }\n"})
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)

    res = cp.Result()
    cp.check_byte_twins(res, [cp.BYTE_TWINS[0]])
    assert res.ok, "identical byte twins must pass"

    (tmp_path / right).write_text("a { color: blue; }\n", encoding="utf-8")
    res = cp.Result()
    cp.check_byte_twins(res, [cp.BYTE_TWINS[0]])
    assert not res.ok
    assert res.findings[0].kind == "byte"


def test_tree_twin_drift_is_detected(tmp_path, monkeypatch) -> None:
    left, right = cp.TREE_TWINS[0]
    _seed(tmp_path, {
        f"{left}/shared.png": "PNG",
        f"{right}/shared.png": "PNG",
    })
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)

    only = [cp.TREE_TWINS[0]]
    res = cp.Result()
    cp.check_tree_twins(res, only)
    assert res.ok

    # a file only the static site has
    (tmp_path / left / "static-only.png").write_text("PNG", encoding="utf-8")
    res = cp.Result()
    cp.check_tree_twins(res, only)
    assert not res.ok and res.findings[0].kind == "tree"

    # and a file whose contents were changed
    (tmp_path / left / "static-only.png").unlink()
    (tmp_path / right / "shared.png").write_text("jpeg", encoding="utf-8")
    res = cp.Result()
    cp.check_tree_twins(res, only)
    assert not res.ok and "contents differ" in res.findings[0].detail


def test_mirror_twin_body_and_surface_drift_are_detected(tmp_path, monkeypatch) -> None:
    twin = cp.MIRROR_TWINS[0]
    static_rel, next_rel = twin.static[0], twin.next[0]
    _seed(tmp_path, {
        static_rel: '(() => {\n  const N = 10;\n  window.ART = { paint };\n})();\n',
        next_rel: 'const ART = (() => {\n  const N = 10;\n  return { paint };\n})();\nexport default ART;\n',
    })
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)
    only = [twin]

    res = cp.Result()
    cp.check_mirror_twins(res, only)
    assert res.ok, "equivalent wrapper styles must not be reported as drift"

    # body change on one side only
    (tmp_path / next_rel).write_text(
        'const ART = (() => {\n  const N = 11;\n  return { paint };\n})();\nexport default ART;\n',
        encoding="utf-8",
    )
    res = cp.Result()
    cp.check_mirror_twins(res, only)
    assert not res.ok and any(f.kind == "body" for f in res.findings)

    # surface change on one side only
    (tmp_path / next_rel).write_text(
        'const ART = (() => {\n  const N = 10;\n  return { paint, MOTIFS };\n})();\nexport default ART;\n',
        encoding="utf-8",
    )
    res = cp.Result()
    cp.check_mirror_twins(res, only)
    assert not res.ok and any(f.kind == "surface" for f in res.findings)


def test_mirror_twin_missing_file_is_detected(tmp_path, monkeypatch) -> None:
    twin = cp.MIRROR_TWINS[0]
    _seed(tmp_path, {twin.static[0]: "(() => {})();\n"})
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)
    res = cp.Result()
    cp.check_mirror_twins(res, [twin])
    assert not res.ok and res.findings[0].kind == "missing"


def test_adapted_twin_vocabulary_drift_is_detected(tmp_path, monkeypatch) -> None:
    twin = cp.ADAPTED_TWINS[0]
    static_rel, next_rel = twin.static[0], twin.next[0]
    sanctioned = set(twin.sanctioned_static_only)

    shared = 'window.X = { list: ["full_payment", "installments"] };\n'
    _seed(tmp_path, {static_rel: shared, next_rel: 'export const list = ["full_payment", "installments"];\n'})
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)
    only = [twin]

    res = cp.Result()
    cp.check_adapted_twins(res, only)
    assert res.ok, f"shared vocabulary must pass; got {[f.detail for f in res.findings]}"

    # a new domain literal on the static side only — this is the drift case
    (tmp_path / static_rel).write_text(
        shared.replace('"installments"', '"installments", "brand_new_method"'),
        encoding="utf-8",
    )
    res = cp.Result()
    cp.check_adapted_twins(res, only)
    assert not res.ok
    assert res.findings[0].kind == "vocabulary"
    assert "brand_new_method" in res.findings[0].detail
    assert "brand_new_method" not in sanctioned


def test_sanctioned_differences_are_the_only_ones_allowed() -> None:
    """Sanctioned sets must be explicit and non-empty-reasoned."""
    for twin in cp.ADAPTED_TWINS:
        for token, reason in twin.sanctioned_static_only.items():
            assert reason, f"{token} is sanctioned without a reason"
        for token, reason in twin.sanctioned_next_only.items():
            assert reason, f"{token} is sanctioned without a reason"

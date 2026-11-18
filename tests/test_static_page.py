"""Safety check on the web page."""

from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"


def test_page_never_uses_inner_html():
    source = PAGE.read_text(encoding="utf-8")
    assert "innerHTML" not in source
    assert "textContent" in source

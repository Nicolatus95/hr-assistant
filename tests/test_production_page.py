"""Contract of the web page for the API key."""

from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"


def test_page_keeps_the_key_in_session_storage_and_sends_it_in_a_header():
    source = PAGE.read_text(encoding="utf-8")
    assert 'data-testid="api-key"' in source
    assert 'type="password"' in source
    assert "sessionStorage" in source
    assert "localStorage" not in source
    assert "X-API-Key" in source
    assert "Clave inválida" in source
    assert "Demasiadas preguntas; espera" in source

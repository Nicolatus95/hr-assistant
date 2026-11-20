"""Unit tests for PII masking, output validation and the audit trail.

Assumed interfaces (the developer must follow them):

- ``app.pii.mask(text)`` returns ``(masked_text, types)``: the marker of each
  type is ``[TYPE]`` and ``types`` has no repeats, in detection order
  (CARD, CURP, RFC, EMAIL, NSS, PHONE).
- ``app.output_guard.check_output(text, secrets, max_chars)`` returns
  ``(text, reason)``: ``reason`` is ``"html"``, ``"secret"`` or ``None``;
  a blocked text is ``BLOCK_MESSAGE``; a long text is cut and ends in ``…``.
- Audit events: ``agent_selected`` (``agent``, ``reason``), ``auth_failed``
  (``path``) and ``rate_limited`` (``client``).
"""

import json

from app.output_guard import check_output
from app.pii import mask

BLOCK_MESSAGE = "No puedo mostrar esa respuesta. Intenta con otra pregunta."
ASK = {"question": "Who is EMP-0001?"}


def test_card_needs_luhn_and_ids_or_dates_are_not_pii():
    assert mask("Tarjeta 4111 1111 1111 1111 ok") == ("Tarjeta [CARD] ok", ["CARD"])
    assert "CARD" not in mask("Numero 4111111111111112")[1]
    plain = "EMP-0004 ingreso el 2021-07-19"
    assert mask(plain) == (plain, [])


def test_pii_is_masked_in_order_without_double_counting():
    assert mask("GARC850101HDFRRL09") == ("[CURP]", ["CURP"])
    text = (
        "RFC PEÑA850101AB1 y A&B850101XY2, correo ana@example.com, "
        "NSS 12345678901, tel +52 55-1234-5678"
    )
    masked, types = mask(text)
    assert types == ["RFC", "EMAIL", "NSS", "PHONE"]
    for value in ("PEÑA850101AB1", "A&B850101XY2", "ana@example.com", "12345678901"):
        assert value not in masked
    assert masked.count("[RFC]") == 2


def test_output_with_html_or_a_secret_is_blocked():
    secrets = ["api-secret-123456", ""]
    cases = [
        ("Mira <b>esto</b>", "html"),
        ("abre javascript:alert(1)", "html"),
        ("la clave es api-secret-123456", "secret"),
        ("Authorization: Bearer abc", "secret"),
        ("token lsv2_pt_abc", "secret"),
    ]
    for text, reason in cases:
        assert check_output(text, secrets, 1500) == (BLOCK_MESSAGE, reason)
    harmless = "2 < 3 y 5 > 4"
    assert check_output(harmless, secrets, 1500) == (harmless, None)


def test_long_output_is_cut_and_ends_with_an_ellipsis():
    text, reason = check_output("a" * 50, [], 10)
    assert reason is None
    assert text.endswith("…")
    assert len(text) <= 11
    assert check_output("corto", [], 10) == ("corto", None)


def test_security_events_are_audited_without_the_key(
    make_client, read_log, audits
):
    client = make_client(RATE_LIMIT_PER_MINUTE="1")
    wrong = {"X-API-Key": "wrong-key-secret-0000"}
    assert client.post("/ask", json=ASK, headers=wrong).status_code == 401
    assert client.post("/ask", json=ASK).status_code == 200
    assert client.post("/ask", json=ASK).status_code == 429
    events = read_log()
    selected = audits(events, "agent_selected")
    assert (selected[0]["agent"], selected[0]["reason"]) == ("directory", "employee_id")
    assert audits(events, "auth_failed")[0]["path"] == "/ask"
    assert audits(events, "rate_limited")[0]["client"] == "test"
    assert "wrong-key-secret-0000" not in json.dumps(events)

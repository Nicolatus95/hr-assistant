"""End-to-end tests of the HR Assistant page, run against the fake model."""
import os
import re

from playwright.sync_api import Page, expect

NON_BLANK = re.compile(r"\S")


def _open_with_key(page: Page, api_key: str = None) -> None:
    """Open the page and type the API key (E2E_API_KEY by default)."""
    page.goto("/")
    key = os.environ["E2E_API_KEY"] if api_key is None else api_key
    page.get_by_test_id("api-key").fill(key)


def _ask(page: Page, question: str) -> None:
    page.get_by_test_id("question").fill(question)
    page.get_by_test_id("send").click()


def test_user_sees_the_answer_and_the_box_is_cleared_after_sending(page: Page):
    _open_with_key(page)
    _ask(page, "Cuantos empleados hay?")

    expect(page.get_by_test_id("answer")).to_contain_text("Cuantos empleados hay?")
    expect(page.locator("[data-testid=answer] .assistant")).to_have_count(1)
    expect(page.get_by_test_id("question")).to_have_value("")


def test_user_sees_the_request_id_after_an_answer(page: Page):
    _open_with_key(page)
    expect(page.get_by_test_id("request-id")).to_be_empty()

    _ask(page, "Cuantos empleados hay?")

    expect(page.get_by_test_id("request-id")).to_have_text(NON_BLANK)


def test_empty_question_shows_an_error_message_in_spanish(page: Page):
    _open_with_key(page)
    page.get_by_test_id("send").click()

    expect(page.get_by_test_id("answer")).to_have_text(NON_BLANK)
    expect(page.get_by_test_id("answer")).to_contain_text(
        re.compile(r"pregunta|vac[ií]a|error", re.IGNORECASE)
    )


def test_second_question_keeps_the_previous_conversation_on_screen(page: Page):
    _open_with_key(page)
    _ask(page, "Primera pregunta")
    expect(page.locator("[data-testid=answer] .assistant")).to_have_count(1)

    _ask(page, "Segunda pregunta")

    expect(page.locator("[data-testid=answer] .assistant")).to_have_count(2)
    expect(page.get_by_test_id("answer")).to_contain_text("Primera pregunta")
    expect(page.get_by_test_id("answer")).to_contain_text("Segunda pregunta")


def test_request_id_changes_between_two_questions(page: Page):
    _open_with_key(page)
    _ask(page, "Primera pregunta")
    expect(page.get_by_test_id("request-id")).to_have_text(NON_BLANK)
    first_id = page.get_by_test_id("request-id").inner_text()

    _ask(page, "Segunda pregunta")

    expect(page.get_by_test_id("request-id")).not_to_have_text(first_id)


def test_vacation_question_shows_twelve_days_and_the_policies_agent(page: Page):
    _open_with_key(page)
    _ask(page, "Cuantos dias de vacaciones me tocan?")

    expect(page.locator("[data-testid=answer] .assistant")).to_contain_text(
        "12 días"
    )
    expect(page.get_by_test_id("agent")).to_contain_text("policies")


def test_question_with_a_curp_shows_the_notice_and_hides_the_curp(page: Page):
    curp = "GOMC800101HDFRRL09"
    _open_with_key(page)
    _ask(page, f"Mi CURP es {curp}, que me puedes decir?")

    expect(page.get_by_test_id("pii-notice")).to_contain_text("CURP")
    assistant = page.locator("[data-testid=answer] .assistant")
    expect(assistant).to_have_count(1)
    expect(assistant).to_have_text(NON_BLANK)
    expect(assistant).not_to_contain_text(curp)


def test_wrong_api_key_shows_invalid_key_message(page: Page):
    _open_with_key(page, api_key="definitely-not-a-valid-key")
    _ask(page, "Cuantos empleados hay?")

    expect(page.get_by_test_id("answer")).to_contain_text("Clave inválida")
    expect(page.locator("[data-testid=answer] .assistant")).to_have_count(0)

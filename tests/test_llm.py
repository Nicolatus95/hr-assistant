"""Unit tests for the fake model in app.llm."""

import json

import pytest

from app.llm import FakeLLM


@pytest.fixture
def llm(directory):
    return FakeLLM(directory)


def reply(llm, content):
    """Ask the model with one user message and parse its JSON text."""
    return json.loads(llm.complete([{"role": "user", "content": content}]).text)


def test_tool_result_wins_over_an_employee_id(llm):
    body = reply(llm, "Resultado de la herramienta: EMP-0001 Ana")
    assert body["answer"].startswith("Según el directorio: ")
    assert "tool" not in body


def test_employee_id_requests_get_employee(llm):
    body = reply(llm, "¿Quién es EMP-0004?")
    assert body == {"tool": "get_employee", "args": {"employee_id": "EMP-0004"}}


def test_known_department_requests_a_search(llm):
    body = reply(llm, "¿Quiénes trabajan en Ventas?")
    assert body["tool"] == "search_by_department"


def test_other_questions_get_the_help_message(llm):
    body = reply(llm, "Hola")
    assert body == {
        "answer": "Pregúntame por un empleado (EMP-0001) o un departamento."
    }


def test_tokens_are_counted_in_words(llm):
    messages = [
        {"role": "user", "content": "uno dos"},
        {"role": "assistant", "content": "tres"},
        {"role": "user", "content": "cuatro cinco"},
    ]
    result = llm.complete(messages)
    assert result.input_tokens == 5
    assert result.output_tokens == len(json.loads(result.text)["answer"].split())

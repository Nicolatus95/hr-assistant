"""Pruebas del ajuste del 20 nov (punto 17.1 y 17.2 de ``spec/05-reto.md``).

Interfaces asumidas (el desarrollador debe seguirlas):

- ``app.router.choose_model`` manda a ``MODEL_LARGE`` con la ruta
  ``keyword:lista`` toda pregunta que contenga la palabra «lista».
- ``app.prompts.PROMPTS`` pide contestar con los datos concretos que pide la
  pregunta (nombres, puestos, fechas, dias) y sigue en 120 palabras o menos.
"""

import pytest

from app.config import load_config
from app.prompts import PROMPTS
from app.router import choose_model

LARGE_MODEL = load_config({}).model_large


def test_list_question_goes_to_the_large_model_with_the_list_route():
    config = load_config({})
    question = "Lista el departamento de Tecnología"
    assert choose_model(question, config) == (LARGE_MODEL, "keyword:lista")


def test_list_keyword_ignores_case():
    config = load_config({})
    assert choose_model("LISTA Ventas", config) == (LARGE_MODEL, "keyword:lista")


def test_question_without_list_word_still_uses_the_small_model():
    config = load_config({})
    model, route = choose_model("Quien es EMP-0001?", config)
    assert (model, route) == (config.model_small, "default")


def test_list_question_reports_the_large_model_through_the_api(make_client):
    client = make_client()
    body = client.post(
        "/ask", json={"question": "Lista Ventas"}
    ).json()
    assert body["model"] == LARGE_MODEL
    assert body["route"] == "keyword:lista"


@pytest.mark.parametrize("agent", ["directory", "policies"])
def test_prompt_asks_for_concrete_data_from_the_tool_result(agent):
    prompt = PROMPTS[agent].lower()
    assert "concretos" in prompt
    assert "nombres" in prompt
    assert "puestos" in prompt
    assert "fechas" in prompt
    assert "días" in prompt or "dias" in prompt


@pytest.mark.parametrize("agent", ["directory", "policies"])
def test_prompt_stays_within_120_words_after_the_adjustment(agent):
    assert len(PROMPTS[agent].split()) <= 120

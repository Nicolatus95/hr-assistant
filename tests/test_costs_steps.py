"""Pasos de los escenarios de costos (pytest-bdd)."""

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/costs.feature")

SMALL_MODEL = "@cf/meta/llama-3.1-8b-instruct-fast"
LARGE_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
ANSWER_BODY = {
    "choices": [{"message": {"content": '{"answer": "Hola"}'}}],
    "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
}


@pytest.fixture
def app_client():
    """Cliente bajo prueba; lo reemplazan los pasos Given."""
    raise AssertionError("a Given step must define the client")


@given(
    "the assistant runs with the default configuration",
    target_fixture="app_client",
)
def default_client(make_client):
    """Servicio con el modelo simulado y la configuracion por omision."""
    return make_client()


@given("the assistant runs with routing disabled", target_fixture="app_client")
def routing_off_client(make_client):
    """Servicio con ROUTING=false."""
    return make_client(ROUTING="false")


@given("the model gateway is down", target_fixture="app_client")
def down_gateway_client(make_gateway_client):
    """Gateway que falla con error de red."""

    def handler(request):
        raise httpx.ConnectError("gateway down", request=request)

    return make_gateway_client(handler)


@given("the model gateway answers from its cache", target_fixture="app_client")
def cached_gateway_client(make_gateway_client):
    """Gateway que responde con ``cf-aig-cache-status: HIT``."""

    def handler(_request):
        headers = {"cf-aig-cache-status": "HIT"}
        return httpx.Response(200, json=ANSWER_BODY, headers=headers)

    return make_gateway_client(handler, CACHE_TTL_SECONDS="60")


@when(parsers.re(r'I ask "(?P<question>[^"]*)"$'), target_fixture="response")
def ask_question(app_client, question):
    """Envia una pregunta."""
    return app_client.post("/ask", json={"question": question})


@when(
    parsers.parse("I ask a question of {size:d} characters"),
    target_fixture="response",
)
def ask_sized_question(app_client, size):
    """Envia una pregunta del largo indicado."""
    return app_client.post("/ask", json={"question": "x" * size})


@then(parsers.parse("the response status is {code:d}"))
def check_status(response, code):
    """Revisa el codigo HTTP."""
    assert response.status_code == code


@then("the model used is the small model")
def check_small_model(response):
    """La respuesta reporta el modelo barato."""
    assert response.json()["model"] == SMALL_MODEL


@then("the model used is the large model")
def check_large_model(response):
    """La respuesta reporta el modelo capaz."""
    assert response.json()["model"] == LARGE_MODEL


@then(parsers.parse('the route is "{route}"'))
def check_route(response, route):
    """La respuesta reporta el motivo del enrutador."""
    assert response.json()["route"] == route


@then("the cost of the answer is greater than zero")
def check_cost_positive(response):
    """Un modelo con precio real cuesta algo."""
    assert response.json()["cost_usd"] > 0


@then("the cost of the answer is zero")
def check_cost_zero(response):
    """Una llamada cacheada no cuesta."""
    assert response.json()["cost_usd"] == 0


@then("the metrics report the same accumulated cost")
def check_metrics_cost(app_client, response):
    """``/metrics`` acumula el costo de la unica respuesta."""
    metrics = app_client.get("/metrics").json()
    assert metrics["cost_usd"] == pytest.approx(response.json()["cost_usd"])


@then('the detail is "model unavailable" with a request id')
def check_bad_gateway(response):
    """El 502 trae el detalle y el id de la peticion."""
    body = response.json()
    assert body["detail"] == "model unavailable"
    assert body["request_id"]


@then("the response does not contain the API token")
def check_no_token(response):
    """El token secreto no se filtra en la respuesta."""
    assert "secret-token" not in response.text


@then("one call is reported as cached")
def check_cached_calls(response):
    """La llamada con HIT cuenta como cacheada."""
    assert response.json()["cached_calls"] == 1

"""Steps for the HR Assistant scenarios (pytest-bdd)."""

from pytest_bdd import parsers, scenarios, then, when

scenarios("features/hr_assistant.feature")


@when(parsers.re(r'I ask "(?P<question>[^"]*)"$'), target_fixture="response")
def ask_question(client, question):
    """Send a single question."""
    return client.post("/ask", json={"question": question})


@when(
    parsers.parse("I ask a question of {size:d} characters"),
    target_fixture="response",
)
def ask_long_question(client, size):
    """Send a question of the given length."""
    return client.post("/ask", json={"question": "a" * size})


@when("I request the health endpoint", target_fixture="response")
def request_health(client):
    """Call GET /health."""
    return client.get("/health")


@when("I open the home page", target_fixture="response")
def open_home(client):
    """Call GET /."""
    return client.get("/")


@when(
    parsers.parse('I ask "{question}" twice, the second time with a history'),
    target_fixture="responses",
)
def ask_twice(client, question):
    """Send the same question twice, the second one with client history."""
    history = [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola, ¿en qué te ayudo?"},
    ]
    first = client.post("/ask", json={"question": question})
    second = client.post("/ask", json={"question": question, "history": history})
    return first, second


@then(parsers.parse("the response status is {code:d}"))
def check_status(response, code):
    """Check the HTTP status code."""
    assert response.status_code == code


@then(parsers.parse('the answer mentions "{text}"'))
def check_answer_mentions(response, text):
    """Check that the answer contains a text."""
    assert text in response.json()["answer"]


@then(parsers.parse('the tools used are "{tool}"'))
def check_tools(response, tool):
    """Check the single tool used."""
    assert response.json()["tools_used"] == [tool]


@then("no tools were used")
def check_no_tools(response):
    """Check that no tool was called."""
    assert response.json()["tools_used"] == []


@then("the answer says the employee was not found")
def check_not_found(response):
    """The answer must say the employee does not exist, without data."""
    answer = response.json()["answer"].lower()
    markers = ("no existe", "not found", "no encontr", "null", "emp-9999")
    assert any(marker in answer for marker in markers)
    assert "jorge" not in answer


@then('the health status is "ok" and it reports a process id')
def check_health(response):
    """Check the health body."""
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["pid"], int)


@then("both answers are identical")
def check_same_answers(responses):
    """Stateless API: the history does not change the outcome."""
    first, second = responses
    assert first.status_code == second.status_code == 200
    assert first.json()["answer"] == second.json()["answer"]


@then(
    parsers.parse(
        'the page contains the test ids "{one}", "{two}" and "{three}"'
    )
)
def check_page(response, one, two, three):
    """Check the three data-testid attributes."""
    for test_id in (one, two, three):
        assert f'data-testid="{test_id}"' in response.text

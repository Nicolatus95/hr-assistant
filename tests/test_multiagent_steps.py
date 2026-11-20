"""Steps for the supervisor and specialists scenarios (pytest-bdd).

Assumed interfaces (the developer must follow them):

- ``POST /ask`` returns ``agent``, ``agent_route`` and ``tools_used``.
- The fake model asks for ``get_policy`` when the last message has a policy
  keyword, and answers with the policy summary.
"""

from pytest_bdd import parsers, scenarios, then, when

scenarios("features/multiagent.feature")


@when(parsers.parse('I ask "{question}"'), target_fixture="response")
def ask_question(client, question):
    """Send one question to the service."""
    return client.post("/ask", json={"question": question})


@then(parsers.parse("the response status is {code:d}"))
def check_status(response, code):
    """Check the HTTP status code."""
    assert response.status_code == code


@then(parsers.parse('the specialist is "{agent}" with the route "{route}"'))
def check_specialist(response, agent, route):
    """Check which specialist answered and why."""
    body = response.json()
    assert body["agent"] == agent
    assert body["agent_route"] == route


@then(parsers.parse('the answer contains "{text}"'))
def check_answer(response, text):
    """The answer carries the expected text."""
    assert text in response.json()["answer"]


@then(parsers.parse('the tools used are "{tools}"'))
def check_tools(response, tools):
    """Check the tools that the specialist ran."""
    assert response.json()["tools_used"] == tools.split(",")

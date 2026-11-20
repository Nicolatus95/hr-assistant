"""Pruebas de la correccion del 19 nov (puntos 3.1 a 3.3) y del orden de auditoria.

Interfaces asumidas (el desarrollador debe seguirlas):

- ``app.prompts.PROMPTS`` explica que hacer con un mensaje que empieza con
  ``Resultado de la herramienta:`` y trae un ejemplo de cada forma del JSON.
- Una herramienta pedida con los mismos argumentos en la misma corrida no se
  ejecuta ni se audita de nuevo; el modelo recibe ``REPEAT_ERROR``.
- Los argumentos desconocidos de una herramienta se ignoran.
- ``agent_selected`` se audita antes que cualquier ``tool_call``.
"""

import json

import pytest

from app.prompts import PROMPTS

REPEAT_ERROR = 'error: ya tienes ese resultado; responde con {"answer": "..."}'
ANSWER = json.dumps({"answer": "Listo"})


def tool_call(name, **args):
    """Texto con el que el modelo pide una herramienta."""
    return json.dumps({"tool": name, "args": args})


@pytest.mark.parametrize("agent", ["directory", "policies"])
def test_prompt_says_what_to_do_with_the_tool_result(agent):
    prompt = PROMPTS[agent]
    assert "Resultado de la herramienta:" in prompt
    assert '{"tool"' in prompt
    assert '{"answer"' in prompt
    assert len(prompt.split()) <= 120


def test_repeated_tool_call_is_not_executed_or_audited_again(
    make_scripted_client, read_log, audits
):
    same = tool_call("get_employee", employee_id="EMP-0001")
    client, llm = make_scripted_client([same, same, ANSWER])
    body = client.post("/ask", json={"question": "Who is EMP-0001?"}).json()
    assert body["answer"] == "Listo"
    assert body["tools_used"] == ["get_employee"]
    assert len(llm.calls) == 3
    assert llm.calls[2][-1]["content"] == REPEAT_ERROR
    assert len(audits(read_log(), "tool_call")) == 1


def test_a_model_that_never_stops_repeating_hits_the_step_cap(
    make_scripted_client, read_log, audits
):
    same = tool_call("get_employee", employee_id="EMP-0001")
    client, llm = make_scripted_client([same], AGENT_MAX_STEPS="4")
    response = client.post("/ask", json={"question": "Who is EMP-0001?"})
    assert response.status_code == 200
    assert len(llm.calls) == 4
    assert response.json()["tools_used"] == ["get_employee"]
    assert len(audits(read_log(), "tool_call")) == 1


def test_same_tool_with_other_arguments_still_runs(make_scripted_client):
    first = tool_call("get_employee", employee_id="EMP-0001")
    second = tool_call("get_employee", employee_id="EMP-0002")
    client, llm = make_scripted_client([first, second, ANSWER])
    body = client.post("/ask", json={"question": "Who is EMP-0001?"}).json()
    assert body["tools_used"] == ["get_employee", "get_employee"]
    assert "Luis" in llm.calls[2][-1]["content"]


def test_unknown_argument_is_ignored_for_the_directory_tool(make_scripted_client):
    call = tool_call("get_employee", employee_id="EMP-0001", year=2024)
    client, llm = make_scripted_client([call, ANSWER])
    body = client.post("/ask", json={"question": "Who is EMP-0001?"}).json()
    assert body["tools_used"] == ["get_employee"]
    feedback = llm.calls[1][-1]["content"]
    assert feedback.startswith("Resultado de la herramienta:")
    assert "Ana" in feedback
    assert "error" not in feedback


def test_unknown_argument_is_ignored_for_the_policies_tool(make_scripted_client):
    call = tool_call("get_policy", topic="vacaciones", year=2024)
    client, llm = make_scripted_client([call, ANSWER])
    body = client.post("/ask", json={"question": "Cuantas vacaciones hay?"}).json()
    assert body["agent"] == "policies"
    assert body["tools_used"] == ["get_policy"]
    assert "POL-VAC" in llm.calls[1][-1]["content"]


def test_agent_selected_is_audited_before_the_specialist_runs(
    make_scripted_client, read_log
):
    call = tool_call("get_employee", employee_id="EMP-0001")
    client, _llm = make_scripted_client([call, ANSWER])
    client.post("/ask", json={"question": "Who is EMP-0001?"})
    actions = [
        e["action"] for e in read_log() if e["event"] == "audit" and "action" in e
    ]
    assert actions.index("agent_selected") < actions.index("tool_call")

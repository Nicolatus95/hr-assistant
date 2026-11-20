"""Tests for the prefetched tool (section 17 of ``spec/05-reto.md``).

Assumed interfaces (the developer must follow them):

- ``app.supervisor.choose_tool(question, reason, departments=())`` returns
  ``(tool, args)`` or ``None``. ``reason`` is the second item of
  ``choose_agent``. For a department, the name returned is the one from
  ``departments`` (with its accents), not the text typed by the user.
- ``Config.prefetch_tools`` is ``True`` by default (``PREFETCH_TOOLS``).
- With ``PREFETCH_TOOLS=true`` the specialist runs the tool before the first
  model call and appends ``Resultado de la herramienta: ...`` as a user message.
- The audit event ``tool_call`` of that tool has ``prefetched: true``.
- The ``agent_run`` log event and the ``hr_request`` metadata have
  ``prefetched`` (a bool).
- The shared fixtures turn ``PREFETCH_TOOLS`` off by default (baseline), so
  every test here that needs the feature turns it on explicitly.
"""

import json
from pathlib import Path

import pytest
from conftest import FakeLangSmith
from fastapi.testclient import TestClient

from app.config import load_config
from app.main import create_app
from app.policies import Policies
from app.supervisor import choose_agent, choose_tool
from app.tracing import build_tracer

POLICIES_FILE = Path(__file__).resolve().parents[1] / "data" / "policies.json"
DEPARTMENTS = ("Tecnología", "Ventas", "Finanzas")
RESULT_PREFIX = "Resultado de la herramienta: "
REPEAT_ERROR = 'error: ya tienes ese resultado; responde con {"answer": "..."}'
ANSWER = json.dumps({"answer": "Listo"})
ON = {"PREFETCH_TOOLS": "true"}


def tool_call(name, **args):
    """Text with which the model asks for a tool."""
    return json.dumps({"tool": name, "args": args})


@pytest.fixture
def policies():
    """Policies loaded from the sample file."""
    return Policies(POLICIES_FILE)


# --- What the supervisor indicates -----------------------------------------


def test_employee_id_prefetches_get_employee_with_the_first_id():
    question = "Compara EMP-0002 con EMP-0001"
    tool = choose_tool(question, "employee_id", DEPARTMENTS)
    assert tool == ("get_employee", {"employee_id": "EMP-0002"})


def test_department_prefetches_search_by_department_with_the_found_name():
    tool = choose_tool("Quien trabaja en tecnologia?", "department", DEPARTMENTS)
    assert tool == ("search_by_department", {"department": "Tecnología"})


def test_policy_reason_prefetches_get_policy_with_that_keyword(policies):
    question = "Cuantas vacaciones me tocan?"
    _agent, reason = choose_agent(question, policies)
    assert choose_tool(question, reason, DEPARTMENTS) == (
        "get_policy",
        {"topic": "vacaciones"},
    )


def test_default_reason_prefetches_nothing():
    assert choose_tool("Hola, buenos dias", "default", DEPARTMENTS) is None


# --- What the specialist does with it --------------------------------------


def test_prefetched_result_reaches_the_model_before_its_first_call(
    make_scripted_client,
):
    client, llm = make_scripted_client([ANSWER], **ON)
    body = client.post("/ask", json={"question": "Who is EMP-0001?"}).json()
    assert body["answer"] == "Listo"
    assert len(llm.calls) == 1
    last = llm.calls[0][-1]
    assert last["role"] == "user"
    assert last["content"].startswith(RESULT_PREFIX)
    assert "Ana" in last["content"]


def test_prefetched_tool_counts_as_a_step_and_is_in_tools_used(make_scripted_client):
    client, llm = make_scripted_client([ANSWER], **ON)
    body = client.post("/ask", json={"question": "Who is EMP-0001?"}).json()
    assert body["tools_used"] == ["get_employee"]
    assert body["steps"] == 2
    assert len(llm.calls) == 1


def test_prefetch_uses_one_of_the_steps_of_the_cap(make_scripted_client):
    # With a cap of 2 the model gets only one call after the prefetch.
    other = tool_call("get_employee", employee_id="EMP-0002")
    client, llm = make_scripted_client([other], AGENT_MAX_STEPS="2", **ON)
    response = client.post("/ask", json={"question": "Who is EMP-0001?"})
    body = response.json()
    assert response.status_code == 200
    assert len(llm.calls) == 1
    assert body["steps"] == 2
    assert body["tools_used"] == ["get_employee", "get_employee"]


def test_prefetched_tool_is_audited_once_with_the_prefetched_flag(
    make_scripted_client, read_log, audits
):
    client, _llm = make_scripted_client([ANSWER], **ON)
    client.post("/ask", json={"question": "Who is EMP-0001?"})
    calls = audits(read_log(), "tool_call")
    assert len(calls) == 1
    assert calls[0]["tool"] == "get_employee"
    assert calls[0]["args"] == {"employee_id": "EMP-0001"}
    assert calls[0]["agent"] == "directory"
    assert calls[0]["prefetched"] is True


def test_model_asking_the_same_tool_again_gets_the_repeat_error(
    make_scripted_client, read_log, audits
):
    same = tool_call("get_employee", employee_id="EMP-0001")
    client, llm = make_scripted_client([same, ANSWER], **ON)
    body = client.post("/ask", json={"question": "Who is EMP-0001?"}).json()
    assert body["answer"] == "Listo"
    assert body["tools_used"] == ["get_employee"]
    assert len(llm.calls) == 2
    assert llm.calls[1][-1]["content"] == REPEAT_ERROR
    assert len(audits(read_log(), "tool_call")) == 1


def test_model_can_still_ask_for_a_different_tool(
    make_scripted_client, read_log, audits
):
    other = tool_call("get_employee", employee_id="EMP-0002")
    client, llm = make_scripted_client([other, ANSWER], **ON)
    body = client.post("/ask", json={"question": "Who is EMP-0001?"}).json()
    assert body["tools_used"] == ["get_employee", "get_employee"]
    assert "Luis" in llm.calls[1][-1]["content"]
    flags = [e.get("prefetched", False) for e in audits(read_log(), "tool_call")]
    assert flags == [True, False]


def test_department_question_prefetches_the_department_search(make_scripted_client):
    client, llm = make_scripted_client([ANSWER], **ON)
    body = client.post("/ask", json={"question": "Quien trabaja en Ventas?"}).json()
    assert body["tools_used"] == ["search_by_department"]
    assert RESULT_PREFIX in llm.calls[0][-1]["content"]


def test_default_question_runs_no_prefetch_even_when_enabled(
    make_scripted_client, read_log
):
    client, llm = make_scripted_client([ANSWER], **ON)
    body = client.post("/ask", json={"question": "Hola, buenos dias"}).json()
    assert (body["steps"], body["tools_used"]) == (1, [])
    assert llm.calls[0][-1]["content"] == "Hola, buenos dias"
    (event,) = [e for e in read_log() if e["event"] == "agent_run"]
    assert event["prefetched"] is False


def test_fake_model_answers_with_the_prefetched_policy(make_client):
    client = make_client(**ON)
    body = client.post(
        "/ask", json={"question": "Cuantos dias de vacaciones tengo?"}
    ).json()
    assert body["agent"] == "policies"
    assert "12" in body["answer"]
    assert body["tools_used"][0] == "get_policy"


# --- Observability ----------------------------------------------------------


def test_agent_run_event_tells_whether_a_tool_was_prefetched(
    make_scripted_client, read_log
):
    client, _llm = make_scripted_client([ANSWER], **ON)
    client.post("/ask", json={"question": "Who is EMP-0001?"})
    (event,) = [e for e in read_log() if e["event"] == "agent_run"]
    assert event["prefetched"] is True
    assert event["tools"] == ["get_employee"]


def test_trace_keeps_the_tool_span_and_marks_the_request_as_prefetched(
    employees_path, directory, scripted_llm
):
    settings = {
        "EMPLOYEES_PATH": str(employees_path),
        "POLICIES_PATH": str(POLICIES_FILE),
        "API_KEYS": "test:test-key-0123456789",
        "LANGSMITH_TRACING": "true",
        "PREFETCH_TOOLS": "true",
    }
    config = load_config(settings)
    fake = FakeLangSmith()
    tracer = build_tracer(config, {"LANGSMITH_API_KEY": "ls-test-key"}, client=fake)
    app = create_app(config, scripted_llm([ANSWER]), directory, tracer=tracer)
    client = TestClient(app)
    client.headers["X-API-Key"] = "test-key-0123456789"
    client.post("/ask", json={"question": "Who is EMP-0001?"})
    names = [run["name"] for run in fake.runs.values()]
    assert "tool:get_employee" in names
    (root,) = [r for r in fake.runs.values() if r["name"] == "hr_request"]
    assert root["extra"]["metadata"]["prefetched"] is True


# --- The switch -------------------------------------------------------------


def test_prefetch_setting_is_on_by_default_and_rejects_bad_values():
    assert load_config({}).prefetch_tools is True
    assert load_config({"PREFETCH_TOOLS": "false"}).prefetch_tools is False
    with pytest.raises(ValueError):
        load_config({"PREFETCH_TOOLS": "maybe"})


def test_with_prefetch_off_everything_works_as_before(
    make_scripted_client, read_log, audits
):
    call = tool_call("get_employee", employee_id="EMP-0001")
    client, llm = make_scripted_client([call, ANSWER], PREFETCH_TOOLS="false")
    body = client.post("/ask", json={"question": "Who is EMP-0001?"}).json()
    assert llm.calls[0][-1]["content"] == "Who is EMP-0001?"
    assert (body["steps"], body["tools_used"]) == (2, ["get_employee"])
    events = read_log()
    (run,) = [e for e in events if e["event"] == "agent_run"]
    assert run["prefetched"] is False
    (audit,) = audits(events, "tool_call")
    assert not audit.get("prefetched")

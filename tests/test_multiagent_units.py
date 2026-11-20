"""Unit tests for the supervisor, the policies and the specialists.

Assumed interfaces (the developer must follow them):

- ``app.supervisor.choose_agent(question, policies)`` returns the pair
  ``(agent, reason)``; the department rule needs the employee directory, so it
  is checked through the API.
- ``app.policies.Policies(path)``: ``get_policy(topic)`` returns the policy
  dict (with ``id``) or ``None``; ``list_policies()`` returns every policy.
- ``app.prompts.PROMPTS`` is a dict ``{"directory": str, "policies": str}``.
- ``Config`` has ``policies_path``, ``max_history_items``,
  ``max_answer_chars`` and ``langsmith_project``.
- The specialist in charge of ``EMP-0001`` questions is ``directory``; it
  sends the system message first, then the trimmed history, then the question.
"""

import json
from pathlib import Path

import pytest

from app.config import load_config
from app.policies import Policies
from app.prompts import PROMPTS
from app.supervisor import choose_agent

POLICIES_FILE = Path(__file__).resolve().parents[1] / "data" / "policies.json"


@pytest.fixture
def policies():
    """Policies loaded from the sample file."""
    return Policies(POLICIES_FILE)


def test_supervisor_applies_the_rules_in_order(policies):
    assert choose_agent("Who is EMP-0004?", policies) == ("directory", "employee_id")
    assert choose_agent("Cuantas vacaciones hay?", policies) == (
        "policies",
        "policy:vacaciones",
    )
    assert choose_agent("Hola, buenos dias", policies) == ("directory", "default")
    # Known limitation: a cross-domain question goes to the first rule.
    cross = "Cuantos dias de vacaciones tiene EMP-0004?"
    assert choose_agent(cross, policies) == ("directory", "employee_id")


def test_supervisor_ignores_case_and_accents(policies):
    question = "CUÁNTOS DÍAS LIBRES me tocan?"
    assert choose_agent(question, policies) == ("policies", "policy:dias libres")


def test_department_name_goes_to_directory_with_its_reason(client):
    body = client.post("/ask", json={"question": "Quien trabaja en Ventas?"}).json()
    assert (body["agent"], body["agent_route"]) == ("directory", "department")


def test_policy_lookup_by_id_topic_and_keyword(policies):
    assert policies.get_policy("POL-VAC")["id"] == "POL-VAC"
    assert policies.get_policy("Home Office")["id"] == "POL-HO"
    assert policies.get_policy("DÍAS LIBRES")["id"] == "POL-VAC"
    assert len(policies.list_policies()) == 5
    assert policies.get_policy("bitcoin") is None


def test_prompts_are_short_and_list_only_their_own_tools():
    assert all(len(text.split()) <= 120 for text in PROMPTS.values())
    assert "get_employee" in PROMPTS["directory"]
    assert "get_policy" not in PROMPTS["directory"]
    assert "get_policy" in PROMPTS["policies"]
    assert "get_employee" not in PROMPTS["policies"]


def test_tool_of_another_specialist_is_unknown_and_audited(
    make_scripted_client, read_log, audits
):
    call = json.dumps({"tool": "get_policy", "args": {"topic": "vacaciones"}})
    client, llm = make_scripted_client([call, json.dumps({"answer": "No puedo"})])
    body = client.post("/ask", json={"question": "Who is EMP-0001?"}).json()
    assert body["agent"] == "directory"
    assert body["tools_used"] == []
    assert "unknown tool" in llm.calls[1][-1]["content"]
    calls = audits(read_log(), "tool_call")
    assert [(e["tool"], e["agent"]) for e in calls] == [("get_policy", "directory")]


def test_json_inside_a_code_block_is_read(make_scripted_client):
    reply = 'Claro:\n```json\n{"answer": "Listo"}\n```\nFin'
    client, _llm = make_scripted_client([reply])
    body = client.post("/ask", json={"question": "Who is EMP-0001?"}).json()
    assert body["answer"] == "Listo"


def test_system_prompt_stays_first_after_trimming_the_history(make_scripted_client):
    client, llm = make_scripted_client(
        [json.dumps({"answer": "ok"})], HISTORY_WINDOW="2"
    )
    history = [{"role": "user", "content": f"mensaje {i}"} for i in range(10)]
    client.post("/ask", json={"question": "Who is EMP-0001?", "history": history})
    sent = llm.calls[0]
    assert sent[0] == {"role": "system", "content": PROMPTS["directory"]}
    assert [m["role"] for m in sent].count("system") == 1
    contents = [m["content"] for m in sent[1:]]
    assert contents == ["mensaje 8", "mensaje 9", "Who is EMP-0001?"]


def test_new_settings_have_defaults_and_reject_bad_values():
    config = load_config({})
    assert config.policies_path == Path("data/policies.json")
    assert config.max_history_items == 20
    assert config.max_answer_chars == 1500
    assert config.langsmith_project == "hr-assistant-local"
    with pytest.raises(ValueError):
        load_config({"MAX_HISTORY_ITEMS": "0"})
    with pytest.raises(ValueError):
        load_config({"MAX_ANSWER_CHARS": "many"})

"""Unit tests for app.agent using a scripted model."""

import json
from types import SimpleNamespace

from app.agent import Agent

CAP_MESSAGE = "No pude completar la respuesta. Intenta con una pregunta más concreta."


class ScriptedLLM:
    """Model that replays prepared replies and records what it received."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages):
        self.calls.append(list(messages))
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return SimpleNamespace(text=text, input_tokens=10, output_tokens=2)


class AlwaysToolLLM:
    """Model that never answers."""

    def complete(self, _messages):
        text = json.dumps({"tool": "get_employee", "args": {"employee_id": "EMP-0001"}})
        return SimpleNamespace(text=text, input_tokens=1, output_tokens=1)


def make_agent(llm, directory, max_steps=3):
    return Agent(llm, directory, max_steps)


def ask(agent, text="pregunta"):
    return agent.run([{"role": "user", "content": text}])


def test_direct_answer_takes_one_step(directory):
    llm = ScriptedLLM([json.dumps({"answer": "Hola"})])
    result = ask(make_agent(llm, directory))
    assert (result.answer, result.steps, result.tools_used) == ("Hola", 1, [])


def test_tool_result_is_fed_back_and_tokens_are_added(directory):
    tool = {"tool": "get_employee", "args": {"employee_id": "EMP-0004"}}
    llm = ScriptedLLM([json.dumps(tool), json.dumps({"answer": "Es Jorge"})])
    result = ask(make_agent(llm, directory))
    last = llm.calls[1][-1]
    assert last["role"] == "user"
    assert last["content"].startswith("Resultado de la herramienta: ")
    assert "Jorge Díaz" in last["content"]
    assert result.tools_used == ["get_employee"]
    assert result.steps == 2
    assert (result.input_tokens, result.output_tokens) == (20, 4)


def test_unknown_tool_is_reported_to_the_model(directory):
    bad = json.dumps({"tool": "delete_everything", "args": {}})
    llm = ScriptedLLM([bad, json.dumps({"answer": "No puedo"})])
    result = ask(make_agent(llm, directory))
    assert result.answer == "No puedo"
    assert llm.calls[1][-1]["content"].startswith("Resultado de la herramienta: ")
    assert "delete_everything" not in result.tools_used


def test_invalid_json_does_not_break_the_agent(directory):
    llm = ScriptedLLM(["this is not json", json.dumps({"answer": "Listo"})])
    result = ask(make_agent(llm, directory))
    assert result.answer == "Listo"


def test_step_cap_returns_the_fixed_message(directory):
    result = ask(make_agent(AlwaysToolLLM(), directory, max_steps=2))
    assert result.answer == CAP_MESSAGE
    assert result.steps == 2

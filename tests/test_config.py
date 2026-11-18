"""Unit tests for app.config."""

import pytest

from app.config import load_config


def test_defaults_are_used_when_nothing_is_set():
    config = load_config({})
    assert config.model_provider == "fake"
    assert config.agent_max_steps == 3
    assert config.max_question_chars == 2000
    assert str(config.employees_path).replace("\\", "/") == "data/employees.json"


@pytest.mark.parametrize(
    "env",
    [
        {"AGENT_MAX_STEPS": "0"},
        {"AGENT_MAX_STEPS": "many"},
        {"MAX_QUESTION_CHARS": "-1"},
        {"MODEL_PROVIDER": "unknown"},
    ],
)
def test_invalid_values_prevent_startup(env):
    with pytest.raises(ValueError):
        load_config(env)

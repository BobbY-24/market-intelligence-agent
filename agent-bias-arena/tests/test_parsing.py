from __future__ import annotations

import json

import pytest

from agent_bias_arena.agent import Agent, DecisionParseError, parse_decision
from agent_bias_arena.config import ModelConfig
from agent_bias_arena.model_client import MockModelClient
from agent_bias_arena.prompts import PromptStore


def payload() -> dict[str, object]:
    return {
        "selected_candidate": "A",
        "confidence": 0.72,
        "reason_codes": ["skills"],
        "short_rationale": "Candidate A matches the stated criteria.",
    }


def test_direct_json_parsing() -> None:
    assert parse_decision(json.dumps(payload())).selected_candidate == "A"


def test_fenced_json_parsing() -> None:
    raw = f"```json\n{json.dumps(payload())}\n```"
    assert parse_decision(raw).confidence == 0.72


def test_balanced_json_extraction_from_prose() -> None:
    raw = f"Here is the result: {json.dumps(payload())} Thanks."
    assert parse_decision(raw).reason_codes == ["skills"]


def test_malformed_output_is_never_fabricated() -> None:
    with pytest.raises(DecisionParseError):
        parse_decision("Candidate A, probably {not valid")


def test_retry_retains_failed_raw_response(project_root, scenarios) -> None:
    config = ModelConfig(
        backend="mock",
        model_name="mock",
        parse_retries=1,
        mock_malformed_first_attempt=True,
    )
    client = MockModelClient(config, seed=1)
    agent = Agent(
        "A",
        PromptStore(project_root / "prompts").get("system_neutral.txt"),
        client,
        PromptStore(project_root / "prompts"),
        parse_retries=1,
        max_rationale_chars=300,
    )
    record = agent.initial_decision(scenarios[0])
    assert record.valid
    assert len(record.attempts) == 2
    assert record.attempts[0].error is not None
    assert "{selected_candidate" in record.attempts[0].raw_response


def test_retry_exhaustion_marks_decision_invalid(project_root, scenarios) -> None:
    prompts = PromptStore(project_root / "prompts")
    config = ModelConfig(
        backend="mock",
        model_name="mock",
        parse_retries=0,
        mock_malformed_first_attempt=True,
    )
    agent = Agent(
        "A",
        prompts.get("system_neutral.txt"),
        MockModelClient(config, seed=1),
        prompts,
        parse_retries=0,
        max_rationale_chars=300,
    )
    record = agent.initial_decision(scenarios[0])
    assert not record.valid
    assert record.decision is None
    assert record.attempts[0].error is not None


def test_final_requires_changed_field() -> None:
    with pytest.raises(DecisionParseError, match="changed_from_initial_decision"):
        parse_decision(json.dumps(payload()), require_changed=True)

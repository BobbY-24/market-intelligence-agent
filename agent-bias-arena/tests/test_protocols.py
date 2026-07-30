from __future__ import annotations

from agent_bias_arena.agent import Agent
from agent_bias_arena.config import ModelConfig
from agent_bias_arena.model_client import MockModelClient
from agent_bias_arena.prompts import PromptStore, render_scenario
from agent_bias_arena.protocols import InteractiveAgentProtocol, ProtocolContext


def _agent(agent_id, project_root, seed=1):
    prompts = PromptStore(project_root / "prompts")
    config = ModelConfig(
        backend="mock",
        model_name="mock",
        mock_behavior="prefer_a",
        mock_adopt_peer=False,
    )
    client = MockModelClient(config, seed)
    return Agent(
        agent_id,
        prompts.get("system_neutral.txt"),
        client,
        prompts,
        parse_retries=0,
        max_rationale_chars=300,
    )


def _context() -> ProtocolContext:
    return ProtocolContext(
        run_id="test",
        condition="interactive",
        repetition=0,
        seed=1,
        model_backend="mock",
        model_name="mock",
        max_discussion_rounds=1,
        biased_peer_agent="B",
        biased_peer_preferred_pronouns="he/him",
    )


def test_interactive_protocol_message_order(project_root, scenarios) -> None:
    episode = InteractiveAgentProtocol().run(
        scenarios[0], _agent("A", project_root), _agent("B", project_root, 2), _context()
    )
    assert episode.valid
    assert [(message.sender, message.receiver, message.kind) for message in episode.messages] == [
        ("A", "B", "argument"),
        ("B", "A", "response"),
    ]
    assert episode.agent_a_initial is not None
    assert episode.agent_a_final is not None


def test_natural_prompt_excludes_internal_metadata(scenarios) -> None:
    rendered = render_scenario(scenarios[0])
    assert "group_1" not in rendered
    assert "group_2" not in rendered
    assert "pair_id" not in rendered
    assert "she/her" in rendered


def test_agent_does_not_carry_cross_episode_messages(project_root, scenarios) -> None:
    agent = _agent("A", project_root)
    client = agent.model
    agent.initial_decision(scenarios[0])
    agent.initial_decision(scenarios[2])
    assert len(client.requests) == 2
    second_request_text = "\n".join(message["content"] for message in client.requests[1])
    assert scenarios[0].job.title not in second_request_text
    assert scenarios[2].job.title in second_request_text

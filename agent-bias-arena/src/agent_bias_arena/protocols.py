"""Explicit experimental protocols with no hidden agent-framework behavior."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .agent import Agent
from .schemas import Decision, DecisionRecord, EpisodeRecord, HiringScenario, MessageRecord


@dataclass(frozen=True)
class ProtocolContext:
    """Metadata shared by every protocol invocation."""

    run_id: str
    condition: str
    repetition: int
    seed: int
    model_backend: str
    model_name: str
    max_discussion_rounds: int
    biased_peer_agent: str
    biased_peer_preferred_pronouns: str


class Protocol(ABC):
    """Shared interface for one controlled episode."""

    @abstractmethod
    def run(
        self,
        scenario: HiringScenario,
        agent_a: Agent,
        agent_b: Agent | None,
        context: ProtocolContext,
    ) -> EpisodeRecord:
        """Run exactly one bounded episode."""


class SingleAgentProtocol(Protocol):
    """One decision, treated as both initial and final."""

    def run(
        self,
        scenario: HiringScenario,
        agent_a: Agent,
        agent_b: Agent | None,
        context: ProtocolContext,
    ) -> EpisodeRecord:
        started = time.monotonic()
        initial = agent_a.initial_decision(scenario)
        final = _copy_as_final(initial)
        return _episode(
            scenario,
            context,
            started,
            agent_a_initial=initial,
            agent_a_final=final,
            valid=initial.valid,
        )


class IndependentAgentProtocol(Protocol):
    """Two agents decide independently and never see each other's outputs."""

    def run(
        self,
        scenario: HiringScenario,
        agent_a: Agent,
        agent_b: Agent | None,
        context: ProtocolContext,
    ) -> EpisodeRecord:
        if agent_b is None:
            raise ValueError("independent protocol requires two agents")
        started = time.monotonic()
        initial_a = agent_a.initial_decision(scenario)
        initial_b = agent_b.initial_decision(scenario)
        return _episode(
            scenario,
            context,
            started,
            agent_a_initial=initial_a,
            agent_b_initial=initial_b,
            agent_a_final=_copy_as_final(initial_a),
            agent_b_final=_copy_as_final(initial_b),
            valid=initial_a.valid and initial_b.valid,
        )


class InteractiveAgentProtocol(Protocol):
    """Two private decisions, bounded public discussion, then private finals."""

    def run(
        self,
        scenario: HiringScenario,
        agent_a: Agent,
        agent_b: Agent | None,
        context: ProtocolContext,
    ) -> EpisodeRecord:
        if agent_b is None:
            raise ValueError("interactive protocol requires two agents")
        started = time.monotonic()
        initial_a = agent_a.initial_decision(scenario)
        initial_b = agent_b.initial_decision(scenario)
        parse_errors = _record_errors(initial_a, initial_b)
        if not initial_a.valid or not initial_b.valid:
            return _episode(
                scenario,
                context,
                started,
                agent_a_initial=initial_a,
                agent_b_initial=initial_b,
                parse_errors=parse_errors,
                valid=False,
            )

        assert initial_a.decision is not None and initial_b.decision is not None
        messages: list[MessageRecord] = []
        previous_response: str | None = None
        for round_number in range(1, context.max_discussion_rounds + 1):
            argument = agent_a.argument(
                scenario,
                initial_a.decision.selected_candidate,
                previous_peer_response=previous_response,
            )
            messages.append(
                MessageRecord(
                    round=round_number,
                    kind="argument",
                    sender=agent_a.agent_id,
                    receiver=agent_b.agent_id,
                    content=argument.content,
                    advocated_candidate=initial_a.decision.selected_candidate,
                    error=argument.error,
                )
            )
            response = agent_b.peer_response(
                scenario,
                initial_b.decision.selected_candidate,
                argument.content,
            )
            messages.append(
                MessageRecord(
                    round=round_number,
                    kind="response",
                    sender=agent_b.agent_id,
                    receiver=agent_a.agent_id,
                    content=response.content,
                    advocated_candidate=initial_b.decision.selected_candidate,
                    error=response.error,
                )
            )
            previous_response = response.content

        message_errors = [message.error for message in messages if message.error]
        transcript = "\n".join(
            f"Round {message.round} — {message.sender}: {message.content}" for message in messages
        )
        final_a = agent_a.final_decision(
            scenario,
            initial_a.decision.selected_candidate,
            transcript,
            peer_recommendation=messages[-1].advocated_candidate,
        )
        last_a_argument = next(
            message for message in reversed(messages) if message.sender == agent_a.agent_id
        )
        final_b = agent_b.final_decision(
            scenario,
            initial_b.decision.selected_candidate,
            transcript,
            peer_recommendation=last_a_argument.advocated_candidate,
        )
        parse_errors.extend(_record_errors(final_a, final_b))
        parse_errors.extend(str(error) for error in message_errors)
        valid = final_a.valid and final_b.valid and not message_errors

        manipulation = None
        adopted = None
        if context.condition == "biased_peer":
            manipulation = {
                "type": "explicit_experimental_tie_break_preference",
                "agent_id": context.biased_peer_agent,
                "preferred_pronouns": context.biased_peer_preferred_pronouns,
                "label": "experimentally_injected",
            }
            neutral_initial = initial_a if context.biased_peer_agent == "B" else initial_b
            neutral_final = final_a if context.biased_peer_agent == "B" else final_b
            preferred_candidate = _candidate_with_pronouns(
                scenario, context.biased_peer_preferred_pronouns
            )
            if neutral_initial.decision and neutral_final.decision:
                adopted = (
                    neutral_initial.decision.selected_candidate != preferred_candidate
                    and neutral_final.decision.selected_candidate == preferred_candidate
                )

        return _episode(
            scenario,
            context,
            started,
            agent_a_initial=initial_a,
            agent_b_initial=initial_b,
            messages=messages,
            agent_a_final=final_a,
            agent_b_final=final_b,
            manipulation=manipulation,
            neutral_agent_adopted_biased_preference=adopted,
            parse_errors=parse_errors,
            valid=valid,
        )


def get_protocol(condition: str) -> Protocol:
    """Return the protocol implementation for a configured condition."""
    if condition == "single":
        return SingleAgentProtocol()
    if condition == "independent":
        return IndependentAgentProtocol()
    if condition in {"interactive", "biased_peer"}:
        return InteractiveAgentProtocol()
    raise ValueError(f"Unknown condition: {condition}")


def _copy_as_final(record: DecisionRecord) -> DecisionRecord:
    decision = record.decision
    if decision is not None:
        decision = Decision(
            **decision.model_dump(exclude={"changed_from_initial_decision"}),
            changed_from_initial_decision=False,
        )
    return DecisionRecord(
        agent_id=record.agent_id,
        stage="final",
        decision=decision,
        raw_response=record.raw_response,
        # No second model request occurred; do not double-count the initial attempts.
        attempts=[],
        valid=record.valid,
    )


def _record_errors(*records: DecisionRecord) -> list[str]:
    return [
        f"{record.agent_id}/{record.stage}/attempt-{attempt.attempt}: {attempt.error}"
        for record in records
        for attempt in record.attempts
        if attempt.error
    ]


def _candidate_with_pronouns(scenario: HiringScenario, pronouns: str) -> str:
    if scenario.candidate_a.pronouns == pronouns:
        return "A"
    return "B"


def _episode(
    scenario: HiringScenario,
    context: ProtocolContext,
    started: float,
    **values: object,
) -> EpisodeRecord:
    return EpisodeRecord(
        run_id=context.run_id,
        episode_id=(f"{scenario.scenario_id}__{context.condition}__rep-{context.repetition:03d}"),
        scenario_id=scenario.scenario_id,
        pair_id=scenario.pair_id,
        variant=scenario.variant,
        condition=context.condition,
        repetition=context.repetition,
        seed=context.seed,
        model_backend=context.model_backend,
        model_name=context.model_name,
        candidate_demographics={
            "A": scenario.candidate_a.demographic_group,
            "B": scenario.candidate_b.demographic_group,
        },
        candidate_pronouns={
            "A": scenario.candidate_a.pronouns,
            "B": scenario.candidate_b.pronouns,
        },
        latency_seconds=time.monotonic() - started,
        **values,
    )

"""Episode-local agent behavior and robust structured-output parsing."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .model_client import ChatMessage, ModelClient, ModelClientError
from .prompts import PromptStore, render_scenario
from .schemas import Decision, DecisionRecord, HiringScenario, ParseAttempt

LOGGER = logging.getLogger(__name__)


class DecisionParseError(ValueError):
    """Raised when no valid decision can be extracted from raw model text."""


def parse_decision(
    raw: str,
    *,
    max_rationale_chars: int = 300,
    require_changed: bool = False,
) -> Decision:
    """Parse direct, fenced, or prose-wrapped JSON and validate its schema."""
    errors: list[str] = []
    candidates = [raw.strip()]
    unfenced = _remove_markdown_fences(raw)
    if unfenced not in candidates:
        candidates.append(unfenced)
    balanced = _first_balanced_object(unfenced)
    if balanced and balanced not in candidates:
        candidates.append(balanced)

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            decision = Decision.model_validate(payload)
            if len(decision.short_rationale) > max_rationale_chars:
                raise ValueError(
                    f"short_rationale exceeds {max_rationale_chars} characters "
                    f"({len(decision.short_rationale)})"
                )
            if require_changed and decision.changed_from_initial_decision is None:
                raise ValueError("changed_from_initial_decision is required for final decisions")
            if not require_changed and decision.changed_from_initial_decision is not None:
                raise ValueError(
                    "changed_from_initial_decision must be omitted for initial decisions"
                )
            return decision
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
            errors.append(str(exc))
    detail = errors[-1] if errors else "no balanced JSON object found"
    raise DecisionParseError(detail)


def _remove_markdown_fences(raw: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else raw.strip()


def _first_balanced_object(raw: str) -> str | None:
    start = raw.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(raw)):
            char = raw[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return raw[start : index + 1]
        start = raw.find("{", start + 1)
    return None


@dataclass(frozen=True)
class GeneratedMessage:
    """Unstructured discussion output and any request error."""

    content: str
    error: str | None = None


class Agent:
    """Stateless prompt orchestrator for one evaluator within one episode."""

    def __init__(
        self,
        agent_id: str,
        system_prompt: str,
        model: ModelClient,
        prompts: PromptStore,
        *,
        parse_retries: int,
        max_rationale_chars: int,
        biased_preferred_pronouns: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.model = model
        self.prompts = prompts
        self.parse_retries = parse_retries
        self.max_rationale_chars = max_rationale_chars
        self.biased_preferred_pronouns = biased_preferred_pronouns

    def initial_decision(self, scenario: HiringScenario) -> DecisionRecord:
        """Request one private initial structured decision."""
        prompt = self.prompts.get("initial_decision.txt").format(
            scenario=render_scenario(scenario),
            max_rationale_chars=self.max_rationale_chars,
        )
        return self._decision_request(prompt, scenario, stage="initial")

    def argument(
        self,
        scenario: HiringScenario,
        initial_choice: str,
        previous_peer_response: str | None = None,
    ) -> GeneratedMessage:
        """Generate a bounded argument without exposing the peer's private decision."""
        prompt = self.prompts.get("argument.txt").format(
            scenario=render_scenario(scenario), initial_choice=initial_choice
        )
        if previous_peer_response:
            prompt += f"\n\nPrevious public peer response:\n{previous_peer_response}"
        return self._message_request(
            prompt,
            scenario,
            stage="argument",
            initial_choice=initial_choice,
        )

    def peer_response(
        self,
        scenario: HiringScenario,
        initial_choice: str,
        peer_argument: str,
    ) -> GeneratedMessage:
        """Respond to the public argument while keeping the private decision private."""
        prompt = self.prompts.get("response.txt").format(
            scenario=render_scenario(scenario),
            initial_choice=initial_choice,
            peer_argument=peer_argument,
        )
        return self._message_request(
            prompt,
            scenario,
            stage="response",
            initial_choice=initial_choice,
        )

    def final_decision(
        self,
        scenario: HiringScenario,
        initial_choice: str,
        transcript: str,
        peer_recommendation: str | None,
    ) -> DecisionRecord:
        """Request a final private decision after the bounded transcript."""
        prompt = self.prompts.get("final_decision.txt").format(
            scenario=render_scenario(scenario),
            initial_choice=initial_choice,
            transcript=transcript,
            max_rationale_chars=self.max_rationale_chars,
        )
        return self._decision_request(
            prompt,
            scenario,
            stage="final",
            initial_choice=initial_choice,
            peer_recommendation=peer_recommendation,
        )

    def _decision_request(
        self,
        prompt: str,
        scenario: HiringScenario,
        *,
        stage: str,
        initial_choice: str | None = None,
        peer_recommendation: str | None = None,
    ) -> DecisionRecord:
        messages: list[ChatMessage] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]
        attempts: list[ParseAttempt] = []
        for attempt_number in range(self.parse_retries + 1):
            raw = ""
            context = self._context(
                scenario,
                stage=stage,
                attempt=attempt_number,
                structured=True,
                initial_choice=initial_choice,
                peer_recommendation=peer_recommendation,
            )
            try:
                raw = self.model.generate(messages, context=context)
                decision = parse_decision(
                    raw,
                    max_rationale_chars=self.max_rationale_chars,
                    require_changed=stage == "final",
                )
                attempts.append(ParseAttempt(attempt=attempt_number, raw_response=raw))
                return DecisionRecord(
                    agent_id=self.agent_id,
                    stage=stage,
                    decision=decision,
                    raw_response=raw,
                    attempts=attempts,
                    valid=True,
                )
            except (DecisionParseError, ModelClientError) as exc:
                LOGGER.warning(
                    "Decision output failed validation for agent=%s stage=%s attempt=%s: %s",
                    self.agent_id,
                    stage,
                    attempt_number,
                    exc,
                )
                attempts.append(
                    ParseAttempt(attempt=attempt_number, raw_response=raw, error=str(exc))
                )
                if attempt_number < self.parse_retries:
                    messages.append({"role": "assistant", "content": raw})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "REPAIR_REQUEST: The previous response failed validation: "
                                f"{exc}. Return only one corrected JSON object matching the schema."
                            ),
                        }
                    )
        return DecisionRecord(
            agent_id=self.agent_id,
            stage=stage,
            decision=None,
            raw_response=attempts[-1].raw_response if attempts else "",
            attempts=attempts,
            valid=False,
        )

    def _message_request(
        self,
        prompt: str,
        scenario: HiringScenario,
        *,
        stage: str,
        initial_choice: str,
    ) -> GeneratedMessage:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]
        try:
            content = self.model.generate(
                messages,
                context=self._context(
                    scenario,
                    stage=stage,
                    attempt=0,
                    structured=False,
                    initial_choice=initial_choice,
                ),
            )
            return GeneratedMessage(content=content)
        except ModelClientError as exc:
            return GeneratedMessage(content="", error=str(exc))

    def _context(self, scenario: HiringScenario, **values: Any) -> dict[str, Any]:
        preferred = None
        if self.biased_preferred_pronouns:
            for candidate in (scenario.candidate_a, scenario.candidate_b):
                if candidate.pronouns == self.biased_preferred_pronouns:
                    preferred = candidate.candidate_id
        return {**values, "biased_preferred_candidate": preferred}

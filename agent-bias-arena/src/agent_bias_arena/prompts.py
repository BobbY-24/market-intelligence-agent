"""Prompt loading and natural candidate-profile rendering."""

from __future__ import annotations

import json
from pathlib import Path

from .schemas import Candidate, HiringScenario

REQUIRED_PROMPTS = (
    "system_neutral.txt",
    "system_biased_peer.txt",
    "initial_decision.txt",
    "argument.txt",
    "response.txt",
    "final_decision.txt",
)


class PromptStore:
    """Validated collection of plain-text prompt templates."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        missing = [name for name in REQUIRED_PROMPTS if not (self.directory / name).is_file()]
        if missing:
            raise FileNotFoundError(f"Missing prompt templates in {self.directory}: {missing}")
        self._templates = {
            name: (self.directory / name).read_text(encoding="utf-8").strip()
            for name in REQUIRED_PROMPTS
        }

    def get(self, name: str) -> str:
        """Return a named prompt template."""
        try:
            return self._templates[name]
        except KeyError as exc:
            raise KeyError(f"Unknown prompt template: {name}") from exc


def render_scenario(scenario: HiringScenario) -> str:
    """Render only natural profile fields; internal group labels never enter prompts."""
    return "\n".join(
        [
            f"Job: {scenario.job.title}",
            f"Description: {scenario.job.description}",
            "",
            _render_candidate(scenario.candidate_a),
            "",
            _render_candidate(scenario.candidate_b),
        ]
    )


def _render_candidate(candidate: Candidate) -> str:
    details = "\n".join(
        f"  - {key.replace('_', ' ').title()}: {_display(value)}"
        for key, value in candidate.qualifications.items()
    )
    return f"Candidate {candidate.candidate_id} (pronouns: {candidate.pronouns}):\n{details}"


def _display(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)

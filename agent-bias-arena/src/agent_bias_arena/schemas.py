"""Pydantic schemas for scenarios, decisions, messages, and episodes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CandidateChoice = Literal["A", "B", "TIE"]


class Job(BaseModel):
    """Fictional job description."""

    model_config = ConfigDict(extra="forbid")
    title: str
    description: str


class Candidate(BaseModel):
    """A fictional candidate with internal demographic annotations."""

    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal["A", "B"]
    demographic_group: Literal["group_1", "group_2"]
    pronouns: Literal["she/her", "he/him"]
    qualifications: dict[str, Any]


class HiringScenario(BaseModel):
    """One original or counterfactually swapped hiring scenario."""

    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    pair_id: str
    variant: Literal["original", "swapped"]
    demographic_dimension: Literal["gender_marker"]
    job: Job
    candidate_a: Candidate
    candidate_b: Candidate

    @model_validator(mode="after")
    def candidate_positions_match(self) -> HiringScenario:
        """Ensure candidate IDs agree with their fixed positions."""
        if self.candidate_a.candidate_id != "A" or self.candidate_b.candidate_id != "B":
            raise ValueError("candidate_a must have ID A and candidate_b must have ID B")
        if self.candidate_a.demographic_group == self.candidate_b.demographic_group:
            raise ValueError("each scenario must contain one member of each synthetic group")
        return self


class Decision(BaseModel):
    """Validated structured model decision."""

    model_config = ConfigDict(extra="forbid")
    selected_candidate: CandidateChoice
    confidence: float = Field(ge=0, le=1)
    reason_codes: list[str]
    short_rationale: str
    changed_from_initial_decision: bool | None = None

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, value: list[str]) -> list[str]:
        if len(value) > 12:
            raise ValueError("reason_codes may contain at most 12 items")
        for code in value:
            if not code.strip() or len(code) > 40:
                raise ValueError("reason codes must be non-empty strings of at most 40 characters")
        return value

    @field_validator("short_rationale")
    @classmethod
    def nonempty_rationale(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("short_rationale must not be empty")
        return value


class ParseAttempt(BaseModel):
    """One raw decision-generation attempt and its parse error, if any."""

    attempt: int
    raw_response: str
    error: str | None = None


class DecisionRecord(BaseModel):
    """Auditable decision with all raw attempts."""

    agent_id: str
    stage: Literal["initial", "final"]
    decision: Decision | None
    raw_response: str
    attempts: list[ParseAttempt]
    valid: bool


class MessageRecord(BaseModel):
    """A natural-language discussion message."""

    round: int
    kind: Literal["argument", "response"]
    sender: str
    receiver: str
    content: str
    advocated_candidate: CandidateChoice | None = None
    error: str | None = None


class EpisodeRecord(BaseModel):
    """Complete, audit-ready episode record."""

    run_id: str
    episode_id: str
    scenario_id: str
    pair_id: str
    variant: Literal["original", "swapped"]
    condition: Literal["single", "independent", "interactive", "biased_peer"]
    repetition: int
    seed: int
    model_backend: str
    model_name: str
    candidate_demographics: dict[str, str]
    candidate_pronouns: dict[str, str]
    agent_a_initial: DecisionRecord | None = None
    agent_b_initial: DecisionRecord | None = None
    messages: list[MessageRecord] = Field(default_factory=list)
    agent_a_final: DecisionRecord | None = None
    agent_b_final: DecisionRecord | None = None
    manipulation: dict[str, Any] | None = None
    neutral_agent_adopted_biased_preference: bool | None = None
    counterfactual_swap_effect: dict[str, bool] | None = None
    parse_errors: list[str] = Field(default_factory=list)
    latency_seconds: float = Field(ge=0)
    valid: bool

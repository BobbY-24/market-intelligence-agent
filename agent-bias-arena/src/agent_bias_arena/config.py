"""Configuration loading, validation, and environment overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Condition = Literal["single", "independent", "interactive", "biased_peer"]


class ExperimentConfig(BaseModel):
    """Experimental design settings."""

    model_config = ConfigDict(extra="forbid")

    name: str = "hiring_bias_mvp"
    seed: int = 42
    repetitions: int = Field(default=3, ge=1)
    conditions: list[Condition] = Field(
        default_factory=lambda: ["single", "independent", "interactive", "biased_peer"]
    )
    max_discussion_rounds: int = Field(default=1, ge=1, le=10)
    bootstrap_repetitions: int = Field(default=1000, ge=0)
    max_rationale_chars: int = Field(default=300, ge=40, le=2000)
    biased_peer_agent: Literal["A", "B"] = "B"
    biased_peer_preferred_pronouns: Literal["she/her", "he/him"] = "he/him"

    @model_validator(mode="after")
    def unique_conditions(self) -> ExperimentConfig:
        """Reject duplicate conditions, which would duplicate episode identifiers."""
        if len(self.conditions) != len(set(self.conditions)):
            raise ValueError("experiment.conditions must not contain duplicates")
        return self


class ModelConfig(BaseModel):
    """Model backend and generation settings."""

    model_config = ConfigDict(extra="forbid")

    backend: Literal["ollama", "mock"] = "ollama"
    model_name: str = "qwen3:4b"
    base_url: str = "http://localhost:11434"
    temperature: float = Field(default=0.2, ge=0)
    top_p: float = Field(default=0.9, gt=0, le=1)
    seed: int | None = None
    timeout_seconds: float = Field(default=120, gt=0)
    request_retries: int = Field(default=2, ge=0, le=10)
    parse_retries: int = Field(default=2, ge=0, le=10)
    max_tokens: int | None = Field(default=500, ge=1)
    mock_behavior: Literal["prefer_a", "prefer_b", "seeded_random", "adopt_peer"] = "seeded_random"
    mock_adopt_peer: bool = True
    mock_malformed_first_attempt: bool = False


class DatasetConfig(BaseModel):
    """Dataset location."""

    model_config = ConfigDict(extra="forbid")
    path: Path


class PromptConfig(BaseModel):
    """Prompt-template directory."""

    model_config = ConfigDict(extra="forbid")
    directory: Path = Path("prompts")


class OutputConfig(BaseModel):
    """Run artifact settings."""

    model_config = ConfigDict(extra="forbid")
    root_dir: Path = Path("results")
    save_raw_responses: bool = True
    save_transcripts: bool = True


class ArenaConfig(BaseModel):
    """Fully resolved arena configuration."""

    model_config = ConfigDict(extra="forbid")

    experiment: ExperimentConfig
    model: ModelConfig
    dataset: DatasetConfig
    prompts: PromptConfig = Field(default_factory=PromptConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


def load_config(path: str | Path) -> ArenaConfig:
    """Load YAML, apply documented environment overrides, and resolve paths."""
    config_path = Path(path).resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Configuration must contain a YAML mapping: {config_path}")

    model = raw.setdefault("model", {})
    output = raw.setdefault("output", {})
    if value := os.getenv("OLLAMA_BASE_URL"):
        model["base_url"] = value
    if value := os.getenv("OLLAMA_MODEL"):
        model["model_name"] = value
    if value := os.getenv("ARENA_RESULTS_DIR"):
        output["root_dir"] = value

    config = ArenaConfig.model_validate(raw)
    project_root = config_path.parent.parent
    config.dataset.path = _resolve(config.dataset.path, project_root)
    config.prompts.directory = _resolve(config.prompts.directory, project_root)
    config.output.root_dir = _resolve(config.output.root_dir, project_root)
    return config


def _resolve(path: Path, root: Path) -> Path:
    return path if path.is_absolute() else (root / path).resolve()


def sanitized_config_dict(config: ArenaConfig) -> dict[str, object]:
    """Return a serializable resolved configuration containing no credentials."""
    return config.model_dump(mode="json")

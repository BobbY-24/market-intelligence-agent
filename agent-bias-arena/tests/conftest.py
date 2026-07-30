"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_bias_arena.dataset import load_dataset
from agent_bias_arena.schemas import HiringScenario


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def scenarios(project_root: Path) -> list[HiringScenario]:
    return load_dataset(project_root / "data/hiring_counterfactual_pairs.jsonl")

"""Experiment orchestration and reproducibility metadata."""

from __future__ import annotations

import hashlib
import logging
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .agent import Agent
from .config import ArenaConfig, sanitized_config_dict
from .dataset import dataset_checksum, load_dataset
from .model_client import create_model_client
from .prompts import PromptStore
from .protocols import ProtocolContext, get_protocol
from .schemas import EpisodeRecord, HiringScenario
from .storage import (
    RunPaths,
    create_run_directory,
    utc_timestamp,
    write_episode_artifacts,
    write_metadata,
    write_resolved_config,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunSelection:
    """Optional CLI filters for an experimental subset."""

    scenario_ids: frozenset[str] | None = None
    conditions: frozenset[str] | None = None
    repetitions: frozenset[int] | None = None


@dataclass(frozen=True)
class DryRunResult:
    """Validated experiment dimensions without model calls."""

    scenarios: int
    conditions: tuple[str, ...]
    repetitions: tuple[int, ...]
    expected_episodes: int


def validate_run(config: ArenaConfig, selection: RunSelection | None = None) -> DryRunResult:
    """Validate config, data, prompts, filters, and expected episode count."""
    scenarios = load_dataset(config.dataset.path)
    PromptStore(config.prompts.directory)
    chosen_scenarios, conditions, repetitions = _select(config, scenarios, selection)
    return DryRunResult(
        scenarios=len(chosen_scenarios),
        conditions=tuple(conditions),
        repetitions=tuple(repetitions),
        expected_episodes=len(chosen_scenarios) * len(conditions) * len(repetitions),
    )


def run_experiment(
    config: ArenaConfig, selection: RunSelection | None = None
) -> tuple[RunPaths, list[EpisodeRecord]]:
    """Run selected episodes and persist canonical artifacts before analysis."""
    scenarios = load_dataset(config.dataset.path)
    prompts = PromptStore(config.prompts.directory)
    chosen_scenarios, conditions, repetitions = _select(config, scenarios, selection)
    paths = create_run_directory(config.output.root_dir, config.experiment.name)
    run_id = paths.root.name
    write_resolved_config(paths, sanitized_config_dict(config))

    episodes: list[EpisodeRecord] = []
    for scenario in chosen_scenarios:
        for condition in conditions:
            for repetition in repetitions:
                episode_seed = _stable_seed(
                    config.experiment.seed,
                    # Paired variants share a seed so marker swaps are not confounded
                    # by an unrelated sampling stream.
                    scenario.pair_id,
                    condition,
                    repetition,
                )
                agent_a, agent_b = _build_agents(config, prompts, scenario, condition, episode_seed)
                context = ProtocolContext(
                    run_id=run_id,
                    condition=condition,
                    repetition=repetition,
                    seed=episode_seed,
                    model_backend=config.model.backend,
                    model_name=config.model.model_name,
                    max_discussion_rounds=config.experiment.max_discussion_rounds,
                    biased_peer_agent=config.experiment.biased_peer_agent,
                    biased_peer_preferred_pronouns=(
                        config.experiment.biased_peer_preferred_pronouns
                    ),
                )
                LOGGER.info("Running %s", f"{scenario.scenario_id}/{condition}/{repetition}")
                episodes.append(get_protocol(condition).run(scenario, agent_a, agent_b, context))

    _annotate_biased_counterfactual_effects(episodes)
    write_episode_artifacts(paths, episodes)
    metadata = _metadata(config, paths, episodes, len(chosen_scenarios))
    write_metadata(paths, metadata)
    return paths, episodes


def _select(
    config: ArenaConfig,
    scenarios: list[HiringScenario],
    selection: RunSelection | None,
) -> tuple[list[HiringScenario], list[str], list[int]]:
    selection = selection or RunSelection()
    scenario_ids = {scenario.scenario_id for scenario in scenarios}
    if selection.scenario_ids:
        missing = selection.scenario_ids - scenario_ids
        if missing:
            raise ValueError(f"Unknown scenario IDs: {sorted(missing)}")
        scenarios = [s for s in scenarios if s.scenario_id in selection.scenario_ids]
    conditions = list(config.experiment.conditions)
    if selection.conditions:
        missing_conditions = selection.conditions - set(conditions)
        if missing_conditions:
            raise ValueError(f"Conditions not enabled in config: {sorted(missing_conditions)}")
        conditions = [value for value in conditions if value in selection.conditions]
    repetitions = list(range(config.experiment.repetitions))
    if selection.repetitions:
        invalid = selection.repetitions - set(repetitions)
        if invalid:
            raise ValueError(f"Repetition indexes out of range: {sorted(invalid)}")
        repetitions = [value for value in repetitions if value in selection.repetitions]
    if not scenarios or not conditions or not repetitions:
        raise ValueError("Selection must include at least one scenario, condition, and repetition")
    return scenarios, conditions, repetitions


def _build_agents(
    config: ArenaConfig,
    prompts: PromptStore,
    scenario: HiringScenario,
    condition: str,
    episode_seed: int,
) -> tuple[Agent, Agent | None]:
    del scenario  # Fresh agents are built per scenario; no scenario state is retained.
    neutral = prompts.get("system_neutral.txt")
    biased = prompts.get("system_biased_peer.txt").format(
        preferred_pronouns=config.experiment.biased_peer_preferred_pronouns
    )

    def build(agent_id: str) -> Agent:
        is_biased = condition == "biased_peer" and config.experiment.biased_peer_agent == agent_id
        agent_seed = _stable_seed(episode_seed, agent_id)
        model_config = config.model.model_copy(
            update={"seed": agent_seed if config.model.seed is not None else None}
        )
        return Agent(
            agent_id,
            biased if is_biased else neutral,
            create_model_client(model_config, agent_seed),
            prompts,
            parse_retries=config.model.parse_retries,
            max_rationale_chars=config.experiment.max_rationale_chars,
            biased_preferred_pronouns=(
                config.experiment.biased_peer_preferred_pronouns if is_biased else None
            ),
        )

    agent_a = build("A")
    agent_b = None if condition == "single" else build("B")
    return agent_a, agent_b


def _stable_seed(*values: object) -> int:
    digest = hashlib.sha256("|".join(map(str, values)).encode()).digest()
    return int.from_bytes(digest[:4], "big")


def _annotate_biased_counterfactual_effects(episodes: list[EpisodeRecord]) -> None:
    grouped: dict[tuple[str, int], list[EpisodeRecord]] = {}
    for episode in episodes:
        if episode.condition == "biased_peer":
            grouped.setdefault((episode.pair_id, episode.repetition), []).append(episode)
    for pair in grouped.values():
        if len(pair) != 2:
            continue
        original = next((item for item in pair if item.variant == "original"), None)
        swapped = next((item for item in pair if item.variant == "swapped"), None)
        if not original or not swapped or not original.manipulation:
            continue
        biased_agent = original.manipulation["agent_id"]
        field = "agent_a_final" if biased_agent == "A" else "agent_b_final"
        before = getattr(original, field)
        after = getattr(swapped, field)
        if not before or not after or not before.decision or not after.decision:
            continue
        before_choice = before.decision.selected_candidate
        after_choice = after.decision.selected_candidate
        before_group = original.candidate_demographics.get(before_choice, before_choice)
        after_group = swapped.candidate_demographics.get(after_choice, after_choice)
        effect = {
            "candidate_position_changed": before_choice != after_choice,
            "selected_demographic_group_changed": before_group != after_group,
        }
        original.counterfactual_swap_effect = effect
        swapped.counterfactual_swap_effect = effect


def _metadata(
    config: ArenaConfig,
    paths: RunPaths,
    episodes: list[EpisodeRecord],
    scenario_count: int,
) -> dict[str, object]:
    return {
        "run_id": paths.root.name,
        "timestamp": utc_timestamp(),
        "git_commit": _git_commit(paths.root.parent),
        "python_version": sys.version,
        "operating_system": platform.platform(),
        "model_backend": config.model.backend,
        "model_name": config.model.model_name,
        "seed": config.experiment.seed,
        "dataset_checksum_sha256": dataset_checksum(config.dataset.path),
        "number_of_scenarios": scenario_count,
        "number_of_completed_episodes": len(episodes),
        "number_of_valid_episodes": sum(episode.valid for episode in episodes),
        "number_of_invalid_episodes": sum(not episode.valid for episode in episodes),
        "number_of_total_episodes": len(episodes),
    }


def _git_commit(cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None

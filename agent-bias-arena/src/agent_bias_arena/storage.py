"""Run-directory creation and durable, auditable artifact storage."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .schemas import DecisionRecord, EpisodeRecord


@dataclass(frozen=True)
class RunPaths:
    """Paths to every required run artifact."""

    root: Path
    config: Path
    metadata: Path
    episodes: Path
    decisions: Path
    transcripts: Path
    invalid_outputs: Path
    metrics: Path
    summary: Path
    plots: Path


def create_run_directory(root_dir: Path, experiment_name: str) -> RunPaths:
    """Create a timestamped unique run directory and plots subdirectory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = root_dir / f"{timestamp}_{_safe_name(experiment_name)}"
    suffix = 1
    while candidate.exists():
        candidate = root_dir / f"{timestamp}_{_safe_name(experiment_name)}_{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    plots = candidate / "plots"
    plots.mkdir()
    return RunPaths(
        root=candidate,
        config=candidate / "config_resolved.yaml",
        metadata=candidate / "run_metadata.json",
        episodes=candidate / "episodes.jsonl",
        decisions=candidate / "decisions.csv",
        transcripts=candidate / "transcripts.jsonl",
        invalid_outputs=candidate / "invalid_outputs.jsonl",
        metrics=candidate / "metrics.json",
        summary=candidate / "summary.md",
        plots=plots,
    )


def paths_for_existing_run(run_dir: str | Path) -> RunPaths:
    """Construct required paths for a previously created run."""
    root = Path(run_dir).resolve()
    return RunPaths(
        root=root,
        config=root / "config_resolved.yaml",
        metadata=root / "run_metadata.json",
        episodes=root / "episodes.jsonl",
        decisions=root / "decisions.csv",
        transcripts=root / "transcripts.jsonl",
        invalid_outputs=root / "invalid_outputs.jsonl",
        metrics=root / "metrics.json",
        summary=root / "summary.md",
        plots=root / "plots",
    )


def write_resolved_config(paths: RunPaths, config: dict[str, Any]) -> None:
    """Write resolved, secret-free YAML configuration."""
    paths.config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def write_metadata(paths: RunPaths, metadata: dict[str, Any]) -> None:
    """Write run metadata as formatted JSON."""
    paths.metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")


def write_episode_artifacts(paths: RunPaths, episodes: list[EpisodeRecord]) -> None:
    """Write canonical episodes plus derived CSV, transcript, and failure files."""
    _write_jsonl(paths.episodes, (episode.model_dump(mode="json") for episode in episodes))
    _write_jsonl(paths.transcripts, _transcript_rows(episodes))
    _write_jsonl(paths.invalid_outputs, _invalid_rows(episodes))
    _write_decisions_csv(paths.decisions, episodes)


def load_episodes(path: str | Path) -> list[EpisodeRecord]:
    """Load canonical saved episode records for re-analysis."""
    return [
        EpisodeRecord.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _transcript_rows(episodes: list[EpisodeRecord]) -> Iterable[dict[str, Any]]:
    for episode in episodes:
        if episode.messages:
            yield {
                "run_id": episode.run_id,
                "episode_id": episode.episode_id,
                "condition": episode.condition,
                "scenario_id": episode.scenario_id,
                "messages": [message.model_dump(mode="json") for message in episode.messages],
            }


def _decision_records(
    episode: EpisodeRecord,
) -> Iterable[tuple[str, str, DecisionRecord]]:
    for field, agent_id, stage in (
        ("agent_a_initial", "A", "initial"),
        ("agent_b_initial", "B", "initial"),
        ("agent_a_final", "A", "final"),
        ("agent_b_final", "B", "final"),
    ):
        record = getattr(episode, field)
        if record is not None:
            yield agent_id, stage, record


def _invalid_rows(episodes: list[EpisodeRecord]) -> Iterable[dict[str, Any]]:
    for episode in episodes:
        for agent_id, stage, record in _decision_records(episode):
            for attempt in record.attempts:
                if attempt.error:
                    yield {
                        "run_id": episode.run_id,
                        "episode_id": episode.episode_id,
                        "condition": episode.condition,
                        "scenario_id": episode.scenario_id,
                        "agent_id": agent_id,
                        "stage": stage,
                        "model_backend": episode.model_backend,
                        **attempt.model_dump(mode="json"),
                        "terminally_invalid": not record.valid,
                    }


def _write_decisions_csv(path: Path, episodes: list[EpisodeRecord]) -> None:
    fields = [
        "run_id",
        "episode_id",
        "scenario_id",
        "pair_id",
        "variant",
        "condition",
        "repetition",
        "agent_id",
        "stage",
        "valid",
        "selected_candidate",
        "selected_demographic_group",
        "confidence",
        "reason_codes",
        "short_rationale",
        "changed_from_initial_decision",
        "raw_response",
        "attempt_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for episode in episodes:
            for agent_id, stage, record in _decision_records(episode):
                decision = record.decision
                selected = decision.selected_candidate if decision else ""
                group = (
                    episode.candidate_demographics.get(selected, "")
                    if selected in {"A", "B"}
                    else selected
                )
                writer.writerow(
                    {
                        "run_id": episode.run_id,
                        "episode_id": episode.episode_id,
                        "scenario_id": episode.scenario_id,
                        "pair_id": episode.pair_id,
                        "variant": episode.variant,
                        "condition": episode.condition,
                        "repetition": episode.repetition,
                        "agent_id": agent_id,
                        "stage": stage,
                        "valid": record.valid,
                        "selected_candidate": selected,
                        "selected_demographic_group": group,
                        "confidence": decision.confidence if decision else "",
                        "reason_codes": json.dumps(decision.reason_codes) if decision else "",
                        "short_rationale": decision.short_rationale if decision else "",
                        "changed_from_initial_decision": (
                            decision.changed_from_initial_decision if decision else ""
                        ),
                        "raw_response": record.raw_response,
                        "attempt_count": len(record.attempts),
                    }
                )


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "-" for char in value)


def utc_timestamp() -> str:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC).isoformat()
